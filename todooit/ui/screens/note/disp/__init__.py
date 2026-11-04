"""
Taking the note's markup and showing it nicely, including as it is typed:

- `markup`   the syntax: constants, regexes, pure line parsing
- `markdown` the markup to and from markdown
- `document` TextArea documents that fold markup out of view and hang wrapped
             list items under their first word
- `theme`    the palette the markup is painted in
- `view`     `NoteView`: draws a note through the documents above
- `typed`    `TypedMarkupView`: turns markup into its drawn form as it's typed

Nothing here knows about keyboard modes or the window around the text.
"""
