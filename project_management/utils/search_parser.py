def get_search_request(keyword):
    if isinstance(keyword, str):
        if keyword.startswith("jql="):
            return "jql", keyword
        else:
            is_project_search = keyword.split("||")
            if len(is_project_search) == 2:
                return "project_text", is_project_search
            else:
                is_ticket = keyword.split('-')
                try:
                    int(is_ticket[1])
                    return "ticket", keyword
                except Exception:
                    return "text", keyword
    else:
        raise TypeError("You have to provide keyword as a string")
