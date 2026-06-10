---
name: pdf-reader
description: >-
  Extracts and reads text content from PDF files using pdftotext (poppler-utils).
  Use when asked to read, summarize, analyze, or search the contents of a PDF file.
allowed-tools: shell
---

# PDF Reader

When asked to read or analyze a PDF file, use `pdftotext` to extract its text content:

    pdftotext -layout "<path/to/file.pdf>" -

The `-layout` flag preserves column layout. The `-` outputs to stdout.
For a specific page range: `pdftotext -f 1 -l 5 -layout file.pdf -`

Always extract the full text first, then answer the user's question from the content.
