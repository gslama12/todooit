"""
Changing the note's text from the keyboard:

- `host`      `EditorHost`: all the editor asks of the window it's in
- `buffer`    `NoteBuffer`: the note as the text `todooit.vim_engine` works on
- `modes`     `ModalEditor`: hosting the engine, and showing the mode it is in
- `editing`   `TextEditing`: enter, nesting, clearing, renumbering
- `clipboard` `ClipboardEditing`: copy, cut and paste
- `normal`    `NormalKeys`: the NORMAL keys the engine doesn't have yet
- `editor`    `NoteEditor`: the bindings, and which key goes where

Builds on `disp` for how the text looks; knows nothing of the window around it.
"""
