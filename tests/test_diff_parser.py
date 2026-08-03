"""Tests built from hand-traced examples."""

from app.diff_parser import parse_unified_diff


def test_single_hunk_with_deletion():
    diff = """diff --git a/src/db.ts b/src/db.ts
--- a/src/db.ts
+++ b/src/db.ts
@@ -10,4 +10,5 @@
 function save(data) {
-  const key = "old";
+  const apiKey = "sk_live_A1b2C3d4E5f6G7h8";
+  console.log(key);
   return db.put(data);
"""
    files = parse_unified_diff(diff)
    assert len(files) == 1
    assert files[0].path == "src/db.ts"
    assert [(a.line, a.content) for a in files[0].added_lines] == [
        (11, '  const apiKey = "sk_live_A1b2C3d4E5f6G7h8";'),
        (12, "  console.log(key);"),
    ]


def test_two_hunks_same_file():
    diff = """diff --git a/src/auth.js b/src/auth.js
--- a/src/auth.js
+++ b/src/auth.js
@@ -8,2 +8,3 @@
 function login(user, pass) {
+  if (pass == null) return false;
   const token = makeToken(user);
@@ -25,3 +26,4 @@
 function logout(token) {
-  console.log(token);
+  // cleanup
+  eval(cleanupScript);
   session.clear();
"""
    files = parse_unified_diff(diff)
    assert len(files) == 1
    assert [(a.line, a.content) for a in files[0].added_lines] == [
        (9, "  if (pass == null) return false;"),
        (27, "  // cleanup"),
        (28, "  eval(cleanupScript);"),
    ]


def test_deletions_only_yield_nothing():
    diff = """diff --git a/config.py b/config.py
--- a/config.py
+++ b/config.py
@@ -3,4 +3,3 @@
 import os
-TOKEN = "abc123"
 DEBUG = True
 PORT = 8080
"""
    files = parse_unified_diff(diff)
    assert files[0].added_lines == []


def test_injection_line_is_inert():
    """An added line that looks like diff syntax must not create a file."""
    diff = """diff --git a/evil.md b/evil.md
--- a/evil.md
+++ b/evil.md
@@ -1,2 +1,4 @@
 intro
+diff --git a/fake b/fake
+@@ -99,1 +99,1 @@
 outro
"""
    files = parse_unified_diff(diff)
    assert len(files) == 1, "injected syntax must not open a new file section"
    assert files[0].path == "evil.md"
    assert [(a.line, a.content) for a in files[0].added_lines] == [
        (2, "diff --git a/fake b/fake"),
        (3, "@@ -99,1 +99,1 @@"),
    ]


def test_indentation_preserved():
    diff = """--- a/x.py
+++ b/x.py
@@ -1,1 +1,2 @@
 a = 1
+        deeply_indented = 2
"""
    assert files_content(diff) == ["        deeply_indented = 2"]


def files_content(diff):
    return [a.content for a in parse_unified_diff(diff)[0].added_lines]


def test_garbage_is_not_a_diff():
    assert parse_unified_diff("") == []
    assert parse_unified_diff("just some prose, no diff here") == []
    assert parse_unified_diff('{"json": true}') == []
