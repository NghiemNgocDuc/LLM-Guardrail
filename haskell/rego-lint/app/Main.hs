module Main (main) where

import Control.Monad (when)
import System.Environment (getArgs)
import System.Exit (ExitCode (..), exitWith)
import System.IO (hGetContents, hPutStrLn, stderr, stdin)

import RegoLint (Issue, lintFile, lintText, renderIssues)

usage :: String
usage = unlines
  [ "usage: rego-lint [FILE|-]"
  , ""
  , "Lint a Rego file (or stdin with '-', the default). Issues are printed"
  , "one per line as FILE:LINE:COL: error: MESSAGE on stderr."
  , ""
  , "exit status: 0 = clean, 1 = at least one issue, 64 = bad usage,"
  , "74 = unreadable input file"
  ]

main :: IO ()
main = do
  args <- getArgs
  case args of
    ["--help"] -> putStr usage >> exitWith ExitSuccess
    ["--version"] -> putStrLn "rego-lint 0.1.0" >> exitWith ExitSuccess
    [fp] -> runFile fp
    _ -> hPutStrLn stderr usage >> exitWith (ExitFailure 64)

runFile :: FilePath -> IO ()
runFile fp
  | fp == "-" = do
      src <- hGetContents stdin
      report Nothing (lintText src)
  | otherwise = do
      r <- lintFile fp
      case r of
        Left e -> hPutStrLn stderr ("rego-lint: " ++ show e) >> exitWith (ExitFailure 74)
        Right issues -> report (Just fp) issues

report :: Maybe FilePath -> [Issue] -> IO ()
report mfile issues = do
  mapM_ (hPutStrLn stderr) (renderIssues mfile issues)
  when (not (null issues)) (exitWith (ExitFailure 1))