-- | rego-lint: offline Rego syntax linter for OPA custom guardrail rules.
--
-- Catches what OPA rejects at parse time WITHOUT an OPA round trip:
--
--   * lexer: illegal characters, unterminated strings, malformed numbers
--   * parser: unbalanced brackets, stray closing brackets, malformed
--     package/import/default statements
--   * heuristics: missing package, statement before package, duplicate
--     package, rule head with no body or value (mirrors OPA's
--     "rule must have a body or value" parse error)
--
-- Output is one line per issue:
--
--   @file:line:col: error: message@
--
-- Exit status 0 = clean, 1 = at least one issue. Zero runtime dependencies
-- beyond base.
module RegoLint
  ( Issue
  , lintText
  , lintFile
  , renderIssues
  ) where

import Control.Exception (IOException, try)
import Data.Char (isAlpha, isAlphaNum, isDigit, isSpace)

-- | A diagnostic: (line, column, message). 1-based, matching OPA's own
-- parse-error reporting.
type Issue = (Int, Int, String)

type Pos = (Int, Int)

-- | Build an Issue from a position.
issueAt :: Pos -> String -> Issue
issueAt (l, c) msg = (l, c, msg)

-- ---------------------------------------------------------------------------
-- Lexer
-- ---------------------------------------------------------------------------

data Keyword = KPackage | KImport | KDefault | KIf | KContains | KAs
             | KSome | KNot | KWith | KElse | KEvery | KIn
  deriving (Eq, Show)

keywords :: [(String, Keyword)]
keywords =
  [ ("package", KPackage), ("import", KImport), ("default", KDefault)
  , ("if", KIf), ("contains", KContains), ("as", KAs)
  , ("some", KSome), ("not", KNot), ("with", KWith), ("else", KElse)
  , ("every", KEvery), ("in", KIn)
  ]

data Token = TIdent Pos String | TStr Pos String | TNum Pos String
           | TKw Pos Keyword | TPunct Pos Char | TNewline
  deriving (Eq, Show)

tokPos :: Token -> Pos
tokPos (TIdent p _) = p
tokPos (TStr p _) = p
tokPos (TNum p _) = p
tokPos (TKw p _) = p
tokPos (TPunct p _) = p
tokPos TNewline = (0, 0)

-- | Lex Rego source into tokens. Newlines become @TNewline@ tokens, but are
-- suppressed while inside brackets so multi-line expressions parse as one
-- statement. All lexer errors are collected (not fail-fast).
lexRego :: String -> ([Issue], [Token])
lexRego src = go 1 1 0 src
  where
    go _ _ _ [] = ([], [])
    go l c d (x : xs)
      | x == '\n' =
          let (is, ts) = go (l + 1) 1 d xs
          in (is, if d == 0 then TNewline : ts else ts)
      | isSpace x =
          let (is, ts) = go l (c + 1) d xs in (is, ts)
      | x == '#' =
          let (is, ts) = skipComment l c d xs in (is, ts)
      | x == '"' =
          let (content, rest, (nl, nc), mIssue) = strBody (l, c) (l, c + 1) [] xs
              (is, ts) = go nl nc d rest
              is' = maybe id (:) mIssue is
          in (is', TStr (l, c) content : ts)
      | isDigit x =
          let (digits, rest, (nl, nc), mIssue) = numBody (l, c) (x : xs)
              (is, ts) = go nl nc d rest
              is' = maybe id (:) mIssue is
          in (is', TNum (l, c) digits : ts)
      | isAlpha x || x == '_' =
          let (w, rest, (nl, nc)) = spanWord (l, c) (x : xs)
              (is, ts) = go nl nc d rest
          in (is, maybe (TIdent (l, c) w) (TKw (l, c)) (lookup w keywords) : ts)
      | x `elem` ("{}[](),;:+-*/%=<>|&." :: String) =
          let d' = d + case x of
                    '{' -> 1
                    '[' -> 1
                    '(' -> 1
                    '}' -> -1
                    ']' -> -1
                    ')' -> -1
                    _ -> 0
              (is, ts) = go l (c + 1) d' xs
          in (is, TPunct (l, c) x : ts)
      | otherwise =
          let (is, ts) = go l (c + 1) d xs
          in ((l, c, "illegal character '" ++ [x] ++ "'") : is, ts)

    skipComment :: Int -> Int -> Int -> String -> ([Issue], [Token])
    skipComment l c d (x : xs)
      | x == '\n' = go l c d (x : xs)
      | otherwise = skipComment l (c + 1) d xs
    skipComment l c d [] = go l c d []

    strBody :: Pos -> Pos -> String -> String -> (String, String, Pos, Maybe Issue)
    strBody sp (ln, cn) acc ('\\' : x : rest) = strBody sp (ln, cn + 2) (x : acc) rest
    strBody sp (ln, cn) acc ('"' : rest) = (reverse acc, rest, (ln, cn + 1), Nothing)
    strBody sp (ln, cn) acc (x : rest) = strBody sp (ln, cn + 1) (x : acc) rest
    strBody sp _ acc [] = (reverse acc, [], (0, 0), Just (issueAt sp "unterminated string literal"))

    numBody :: Pos -> String -> (String, String, Pos, Maybe Issue)
    numBody (ln, cn) s =
      let (a, b) = span (\x -> isDigit x || x == '.') s
          dots = length (filter (== '.') a)
          bad = dots > 1 || (not (null a) && last a == '.')
          issue = if bad then Just (ln, cn, "malformed number '" ++ a ++ "'") else Nothing
      in (a, b, (ln, cn + length a), issue)

    spanWord :: Pos -> String -> (String, String, Pos)
    spanWord (ln, cn) s =
      let (a, b) = span (\x -> isAlphaNum x || x == '_') s
      in (a, b, (ln, cn + length a))

-- ---------------------------------------------------------------------------
-- Parser (statement-level)
-- ---------------------------------------------------------------------------

data Stmt = StmtPackage Pos [String]
          | StmtImport Pos [String] (Maybe String)
          | StmtDefault Pos String Bool
          | StmtRule Pos String Bool Bool  -- name, hasHeadArg, hasBodyOrValue
          | StmtExpr Pos [Token]
  deriving (Show)

stmtPos :: Stmt -> Pos
stmtPos (StmtPackage p _) = p
stmtPos (StmtImport p _ _) = p
stmtPos (StmtDefault p _ _) = p
stmtPos (StmtRule p _ _ _) = p
stmtPos (StmtExpr p _) = p

isSep :: Token -> Bool
isSep TNewline = True
isSep (TPunct _ ';') = True
isSep _ = False

-- | Split a token stream into statements on newline/semicolon at bracket
-- depth 0 (the lexer already suppressed newlines inside brackets).
splitChunks :: [Token] -> [[Token]]
splitChunks ts = case break isSep ts of
  (chunk, []) -> if null chunk then [] else [chunk]
  (chunk, rest) ->
    let rest' = dropWhile isSep rest
    in (if null chunk then [] else [chunk]) ++ splitChunks rest'

scanStatements :: Bool -> [Token] -> ([Issue], [Stmt])
scanStatements top ts =
  let results = map (scanStmt top) (splitChunks ts)
  in (concatMap fst results, concatMap snd results)

scanStmt :: Bool -> [Token] -> ([Issue], [Stmt])
scanStmt _ [] = ([], [])
scanStmt top (t : ts) = case t of
  TKw _ KPackage -> scanPackage t ts
  TKw _ KImport -> scanImport t ts
  TKw _ KDefault -> scanDefault t ts
  TIdent _ name -> scanIdent top name t ts
  TPunct _ '}' -> ([issueAt (tokPos t) "unexpected '}'"], [])
  TPunct _ ')' -> ([issueAt (tokPos t) "unexpected ')'"], [])
  TPunct _ ']' -> ([issueAt (tokPos t) "unexpected ']'"], [])
  _ -> ([], [StmtExpr (tokPos t) (t : ts)])

-- | A dotted identifier path (package / import target).
parsePath :: [Token] -> Either [Issue] ([String], [Token])
parsePath = go []
  where
    go acc (TIdent _ w : d@(TPunct _ '.') : rest) = case rest of
      [] -> Left [issueAt (tokPos d) "trailing '.' in path"]
      _ -> go (w : acc) rest
    go acc (TIdent _ w : rest) = Right (reverse (w : acc), rest)
    go _ [] = Right ([], [])
    go _ (t : _) = Left [issueAt (tokPos t) "expected identifier in path"]

scanPackage :: Token -> [Token] -> ([Issue], [Stmt])
scanPackage t ts = case parsePath ts of
  Left iss -> (iss, [])
  Right (path, rest) ->
    let issues
          | null path = [issueAt (tokPos t) "package path must not be empty"]
          | otherwise = case rest of
              [] -> []
              _ -> [issueAt (tokPos (head rest)) "unexpected tokens after package path"]
    in (issues, [StmtPackage (tokPos t) path])

scanImport :: Token -> [Token] -> ([Issue], [Stmt])
scanImport t ts = case parsePath ts of
  Left iss -> (iss, [])
  Right (path, rest) ->
    let (alias, issues) = case rest of
          [] -> (Nothing, if null path then [issueAt (tokPos t) "import path must not be empty"] else [])
          TKw _ KAs : TIdent _ a : [] -> (Just a, [])
          TKw _ KAs : _ -> (Nothing, [issueAt (tokPos (head rest)) "import `as` must be followed by an identifier"])
          _ -> (Nothing, if null path then [issueAt (tokPos t) "import path must not be empty"] else [issueAt (tokPos (head rest)) "unexpected tokens after import path"])
    in (issues, [StmtImport (tokPos t) path alias])

scanDefault :: Token -> [Token] -> ([Issue], [Stmt])
scanDefault t ts = case ts of
  [] -> ([issueAt (tokPos t) "default must name a rule"], [])
  TIdent _ n : rest ->
    let (hasValue, issues) = case rest of
          [] -> (False, [issueAt (tokPos t) "default rule requires a value (e.g. `default allow := false`)"])
          TPunct _ ':' : TPunct _ '=' : _ -> (True, [])
          TPunct _ '=' : _ -> (True, [])
          _ -> (False, [issueAt (tokPos (head rest)) "default rule requires `:= <value>`"])
    in (issues, [StmtDefault (tokPos t) n hasValue])
  _ -> ([issueAt (tokPos (head ts)) "default must name a rule"], [])

-- | Find the first top-level @{@ and return (tokens inside, tokens after),
-- or the whole stream when there is no brace (used for `if <expr>` bodies).
-- Errors on unbalanced/unterminated braces.
findBraceBody :: [Token] -> Either [Issue] ([Token], [Token])
findBraceBody toks = case break isOpen toks of
  (_, []) -> Right (toks, [])
  (_, openTok : rest) ->
    let (inner, after, issues) = collect 1 [] rest (tokPos openTok)
    in case issues of
      [] -> Right (inner, after)
      _ -> Left issues
  where
    isOpen (TPunct _ '{') = True
    isOpen _ = False
    collect :: Int -> [Token] -> [Token] -> Pos -> ([Token], [Token], [Issue])
    collect 0 acc rest _ = (reverse acc, rest, [])
    collect _ _ [] op = ([], [], [issueAt op "unterminated '{'"])
    collect d acc (TPunct _ '{' : xs) op = collect (d + 1) (TPunct op '{' : acc) xs op
    collect d acc (TPunct _ '}' : xs) op = collect (d - 1) (TPunct op '}' : acc) xs op
    collect d acc (x : xs) op = collect d (x : acc) xs op

isBodyMarker :: Token -> Bool
isBodyMarker (TPunct _ '{') = True
isBodyMarker (TPunct _ ':') = True
isBodyMarker (TPunct _ '=') = True
isBodyMarker (TKw _ KIf) = True
isBodyMarker _ = False

-- | A rule body: `{ ... }`, `if <expr>`, or `:= <value>` (possibly followed
-- by an `if { ... }` body). The head itself never counts as a body.
scanIdent :: Bool -> String -> Token -> [Token] -> ([Issue], [Stmt])
scanIdent top name t ts = case ts of
  TKw _ KContains : _ -> ruleBody ts
  TPunct _ '[' : _ -> ruleBody ts
  TKw _ KIf : _ -> ruleBody ts
  TPunct _ '{' : _ -> ruleBody ts
  TPunct _ ':' : TPunct _ '=' : rest -> valueRule rest
  TPunct _ '=' : rest -> valueRule rest
  []
    | top -> ([issueAt (tokPos t) ("rule '" ++ name ++ "' must have a body or value")],
              [StmtRule (tokPos t) name False False])
    | otherwise -> ([], [StmtExpr (tokPos t) [t]])
  _ -> ([], [StmtExpr (tokPos t) (t : ts)])
  where
    noBody = case ts of
      [] -> True
      TKw _ KIf : rest -> null rest
      _ -> not (any isBodyMarker ts)

    ruleBody toks
      | noBody = ([issueAt (tokPos t) ("rule '" ++ name ++ "' must have a body or value")], [])
      | otherwise = case findBraceBody toks of
          Left iss -> (iss, [])
          Right (inner, rest) ->
            let (i2, _) = scanStatements False inner
                trailing = case rest of
                  [] -> []
                  _ -> [issueAt (tokPos (head rest)) "unexpected tokens after rule body"]
            in (i2 ++ trailing, [StmtRule (tokPos t) name True True])

    valueRule [] = ([issueAt (tokPos t) ("rule '" ++ name ++ "' must have a body or value")], [])
    valueRule rest = case findBraceBody rest of
      Left iss -> (iss, [])
      Right (inner, after) ->
        let (i2, _) = scanStatements False inner
            (i3, restIssues) = case after of
              [] -> ([], [])
              TKw _ KIf : _ -> case findBraceBody after of
                Left iss2 -> (iss2, [])
                Right (inner2, rest2) ->
                  let (i3', _) = scanStatements False inner2
                  in (i3', case rest2 of
                        [] -> []
                        _ -> [issueAt (tokPos (head rest2)) "unexpected tokens after rule body"])
              _ -> ([], [issueAt (tokPos (head after)) "unexpected tokens after rule body"])
        in (i2 ++ i3 ++ restIssues, [StmtRule (tokPos t) name False True])

-- | Whole-file heuristics that need the statement list.
postCheck :: [Stmt] -> [Issue]
postCheck stmts =
  let pkgs = [stmtPos s | s <- stmts, isPkg s]
      before = case stmts of
        (s : _) | not (isPkg s) -> [issueAt (stmtPos s) "statement before package declaration"]
        _ -> []
      dups = [issueAt p "duplicate package declaration" | p <- drop 1 pkgs]
  in case pkgs of
    [] -> [(1, 1, "missing package declaration (e.g. `package guardrails`)")]
    _ -> before ++ dups
  where
    isPkg (StmtPackage _ _) = True
    isPkg _ = False

-- ---------------------------------------------------------------------------
-- Public API
-- ---------------------------------------------------------------------------

-- | Lint Rego source text. Returns all issues (empty = clean).
lintText :: String -> [Issue]
lintText src =
  let (lexIssues, toks) = lexRego src
  in if not (null lexIssues)
       then lexIssues
       else
         let (scanIssues, stmts) = scanStatements True toks
         in scanIssues ++ postCheck stmts

-- | Lint a file. IO errors are returned as @Left@.
lintFile :: FilePath -> IO (Either IOException [Issue])
lintFile fp = do
  r <- try (readFile fp)
  pure (fmap lintText r)

-- | One line per issue, with optional filename prefix:
-- @file:line:col: error: message@
renderIssues :: Maybe FilePath -> [Issue] -> [String]
renderIssues mfile = map render
  where
    prefix = maybe "" (++ ":") mfile
    render (l, c, msg) = prefix ++ show l ++ ":" ++ show c ++ ": error: " ++ msg