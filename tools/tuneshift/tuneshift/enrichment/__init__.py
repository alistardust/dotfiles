"""Search-grounded enrichment pipeline.

Looks up real data (MusicBrainz, Last.fm, Genius) before asking an LLM
to synthesize track metadata. The LLM never guesses from title alone.
"""
