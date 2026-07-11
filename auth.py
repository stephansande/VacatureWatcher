from flask import (
    Blueprint,
    render_template,
    redirect,
    request,
    url_for
)

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required
)

from models import User

from database import db



auth = Blueprint(
    "auth",
    __name__
)



login_manager = LoginManager()



@login_manager.user_loader
def load_user(user_id):

    return db.session.get(
        User,
        int(user_id)
    )




@auth.route(
    "/login",
    methods=[
        "GET",
        "POST"
    ]
)
def login():


    error = None


    if request.method == "POST":


        username = request.form.get(
            "username"
        )


        password = request.form.get(
            "password"
        )



        user = User.query.filter_by(
            username=username
        ).first()



        if user and user.check_password(
            password
        ):


            login_user(
                user,
                remember=False
            )


            return redirect(
                url_for(
                    "dashboard"
                )
            )



        error = (
            "Ongeldige gebruikersnaam of wachtwoord"
        )



    return render_template(
        "login.html",
        error=error
    )




@auth.route(
    "/logout"
)
@login_required
def logout():


    logout_user()


    return redirect(
        url_for(
            "auth.login"
        )
    )
