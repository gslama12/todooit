"""
Taking the note's markdown and showing it nicely:

- `markup`   the syntax: constants, regexes, pure line parsing
- `markdown` what a paste reads, and the old stored format written as markdown
- `document` TextArea documents that fold markup out of view and hang wrapped
             list items under their first word
- `theme`    the palette the markup is painted in
- `view`     `NoteView`: draws a note through the documents above

Nothing here knows about keyboard modes or the window around the text.
"""
