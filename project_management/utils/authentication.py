def auth_cleanup(authen):
    password_splitted = authen.get('psasword', "-").split("-")
    return authen.get("login", ""), password_splitted[0], password_splitted[1]
