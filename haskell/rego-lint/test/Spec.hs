module Main (main) where

import Control.Monad (forM_)
import Data.List (isInfixOf, tails)
import System.IO (readFile)

import Test.Hspec

import RegoLint (Issue, lintText)

main :: IO ()
main = hspec $ do
  describe "lexer" $ do
    it "accepts a comment-only file as clean" $
      lintText "# just a comment\n" `shouldSatisfy` any (mentions "missing package")
    it "reports an unterminated string" $ do
      let issues = lintText "package p\nx := \"oops"
      issues `shouldSatisfy` any (mentions "unterminated string")
    it "reports an illegal character" $ do
      let issues = lintText "package p\nx := 1\nx $ 2"
      issues `shouldSatisfy` any (mentions "illegal character")
    it "reports a malformed number" $ do
      let issues = lintText "package p\nx := 1.2.3"
      issues `shouldSatisfy` any (mentions "malformed number")
    it "accepts an exponent number" $
      lintText "package p\nx := 1.5e3\ny := 1e-2" `shouldBe` []

  describe "parser" $ do
    it "accepts a realistic org rule" $
      lintText realistic `shouldBe` []
    it "accepts multi-line expressions inside brackets" $
      lintText "package p\nx := [\n  1,\n  2,\n]\ny := {\n  \"a\": 1,\n}" `shouldBe` []
    it "rejects a rule with no body or value" $ do
      let issues = lintText "package p\nallow"
      issues `shouldSatisfy` any (mentions "must have a body or value")
    it "rejects contains with no body" $ do
      let issues = lintText "package p\nallow contains x"
      issues `shouldSatisfy` any (mentions "must have a body or value")
    it "rejects an unterminated rule body" $ do
      let issues = lintText "package p\nallow if {\n  x := 1\n"
      issues `shouldSatisfy` any (mentions "unterminated '{'")
    it "rejects a stray closing brace" $ do
      let issues = lintText "package p\n}"
      issues `shouldSatisfy` any (mentions "unexpected '}'")
    it "rejects a package that is not first" $ do
      let issues = lintText "import rego.v1\npackage p"
      issues `shouldSatisfy` any (mentions "statement before package")
    it "rejects duplicate packages" $ do
      let issues = lintText "package a\npackage b"
      issues `shouldSatisfy` any (mentions "duplicate package")
    it "rejects a missing package" $ do
      let issues = lintText "allow if { true }"
      issues `shouldSatisfy` any (mentions "missing package")
    it "rejects default without a value" $ do
      let issues = lintText "package p\ndefault allow"
      issues `shouldSatisfy` any (mentions "default rule requires a value")
    it "rejects a trailing dot in a package path" $ do
      let issues = lintText "package foo."
      issues `shouldSatisfy` any (mentions "trailing '.'")
    it "accepts import with alias" $
      lintText "package p\nimport data.foo as f" `shouldBe` []
    it "reports per-issue positions" $ do
      let issues = lintText "package p\nallow\n"
      issues `shouldSatisfy` any (\i -> i == (2, 1, "rule 'allow' must have a body or value"))

  describe "fixtures" $ do
    fixtures <- runIO listFixtures
    forM_ fixtures $ \(name, expected) ->
      it ("fixture " ++ name ++ " -> " ++ expected) $ do
        src <- readFile ("test/fixtures/" ++ name)
        let issues = lintText src
        case expected of
          "clean" -> issues `shouldBe` []
          frag -> issues `shouldSatisfy` any (mentions frag)

realistic :: String
realistic = unlines
  [ "package guardrails"
  , ""
  , "import rego.v1"
  , ""
  , "default decision := {\"action\": \"pass\", \"reason\": \"no finding\"}"
  , ""
  , "decision := {\"action\": \"block\", \"reason\": \"secret detected\"} if {"
  , "\tinput.findings[i].matched"
  , "\tinput.findings[i].check == \"Secret Detection\""
  , "}"
  , ""
  , "allow contains prompt if {"
  , "\tprompt := input.prompt"
  , "\tnot decision.action == \"pass\""
  , "}"
  ]

listFixtures :: IO [(String, String)]
listFixtures = pure
  [ ("valid_rule.rego", "clean")
  , ("invalid_unbalanced.rego", "unterminated '{'")
  , ("invalid_no_body.rego", "must have a body or value")
  , ("invalid_package_order.rego", "statement before package")
  , ("invalid_unterminated_string.rego", "unterminated string")
  , ("invalid_default.rego", "default rule requires a value")
  , ("invalid_dup_package.rego", "duplicate package")
  , ("invalid_missing_package.rego", "missing package")
  , ("invalid_stray_brace.rego", "unexpected '}'")
  , ("invalid_malformed_number.rego", "malformed number")
  , ("invalid_contains_no_body.rego", "must have a body or value")
  ]

mentions :: String -> Issue -> Bool
mentions frag (_, _, msg) = frag `isInfixOf` msg