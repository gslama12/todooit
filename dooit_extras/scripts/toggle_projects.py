from dooit.ui.api import DooitAPI


def toggle_projects(api: DooitAPI):
    def wrapper():
        """Toggles the visibility of the projects tree"""
        project_switcher = api.app.screen.query_one("#project_switcher")
        todo_switcher = api.app.screen.query_one("#todo_switcher")

        if project_switcher.display:
            project_switcher.display = False
            todo_switcher.styles.column_span = 2
            api.switch_focus()
        else:
            project_switcher.display = True
            todo_switcher.styles.column_span = 1
            api.app.project_tree.focus()

    return wrapper
