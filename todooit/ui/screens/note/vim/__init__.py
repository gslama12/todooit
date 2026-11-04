"""
Changing the note's text from the keyboard:

- `host`      `EditorHost`: all the editor asks of the window it's in
- `modes`     `ModalEditor`: NORMAL and INSERT, and moving between them
- `editing`   `TextEditing`: enter, backspace, nesting, clearing
- `clipboard` `ClipboardEditing`: copy, cut and paste
- `normal`    `NormalKeys`: what each key does in NORMAL
- `editor`    `NoteEditor`: the bindings, and which key goes where

Builds on `disp` for how the text looks; knows nothing of the window around it.
"""
