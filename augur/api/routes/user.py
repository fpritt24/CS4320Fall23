#SPDX-License-Identifier: MIT
"""
Creates routes for user login functionality
"""

import logging
import requests
import json
import os
import base64
import pandas as pd
from flask import request, Response, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.sql import text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound
from augur.application.db.session import DatabaseSession
from augur.tasks.github.util.github_task_session import GithubTaskSession
from augur.util.repo_load_controller import RepoLoadController


from augur.application.db.models import User, UserRepo, UserGroup, UserSessionToken, ClientToken
from augur.application.config import get_development_flag
logger = logging.getLogger(__name__)
development = get_development_flag()
from augur.application.db.engine import create_database_engine
Session = sessionmaker(bind=create_database_engine())

AUGUR_API_VERSION = 'api/unstable'

""" 
    Extract Bearer token from request header,
    using the standard oauth2 format
"""
def get_bearer_token(request):
    token = request.headers.get("Authorization")

    if token and " " in token:
        token = token.split(" ")
        if len(token) == 2:
            return token[1]

        for substr in token:
            if substr and "Bearer" not in substr:
                return substr
    
    return token

def user_login_required(fun):
    def wrapper(*args, **kwargs):
        # TODO check that user session token is valid

        # We still need to decide on the format for this

        user_token = request.args.get("user_token")
        print(user_token)
                    
        # If valid:
        if user_token:

            session = Session()
            try:
                user = session.query(UserSessionToken).filter(UserSessionToken.token == user_token).one().user
                
                return fun(user=user, *args, **kwargs)
            except NoResultFound:
                print("Not found")

        # else: return error JSON
        return {"status": "Invalid user session"}

    wrapper.__name__ = fun.__name__ 
    return wrapper

def api_key_required(fun):
    def wrapper(*args, **kwargs):
        # TODO check that API key is valid

        client_token = request.args.get("client_api_key")
                    
        # If valid:
        if client_token:

            session = Session()
            try:
                session.query(ClientToken).filter(ClientToken.token == client_token).one()
                return fun(*args, **kwargs)
            except NoResultFound:
                pass

        # else: return error JSON
        return {"status": "Unauthorized client"}
    
    wrapper.__name__ = fun.__name__
    return wrapper

# usage:
"""
@app.route("/path")
@api_key_required
@user_login_required
def priviledged_function():
    stuff
"""

# TODO This should probably be available to all endpoints
def generate_upgrade_request():
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/426
    response = jsonify({"status": "SSL Required"})
    response.headers["Upgrade"] = "TLS"
    response.headers["Connection"] = "Upgrade"

    return response, 426

def create_routes(server):
    # TODO This functionality isn't specific to the User endpoints, and should be moved
    @server.app.errorhandler(405)
    def unsupported_method(error):
        return jsonify({"status": "Unsupported method"}), 405

    @server.app.route(f"/{AUGUR_API_VERSION}/user/validate", methods=['POST'])
    def validate_user():
        if not development and not request.is_secure:
            return generate_upgrade_request()

        session = Session()
        username = request.args.get("username")
        password = request.args.get("password")
        if username is None or password is None:
            # https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400
            return jsonify({"status": "Missing argument"}), 400

        user = session.query(User).filter(User.login_name == username).first()
        if user is None:
            return jsonify({"status": "Invalid username"})

        checkPassword = check_password_hash(user.login_hashword, password)
        if checkPassword == False:
            return jsonify({"status": "Invalid password"})

        login_user(user)

        return jsonify({"status": "Validated"})

    @server.app.route(f"/{AUGUR_API_VERSION}/user/logout", methods=['POST'])
    @login_required
    def logout_user_func():
        if not development and not request.is_secure:
            return generate_upgrade_request()

        if logout_user():
            return jsonify({"status": "Logged out"})

        return jsonify({"status": "Error when logging out"})

    
    @server.app.route(f"/{AUGUR_API_VERSION}/user/oauth", methods=['POST'])
    def oauth_validate():
        # Check if user has an active session
        current_session = request.args.get("session")

        if current_session:
            # TODO validate session token
            # If invalid, set current_session to None to force validation
            pass

        if not current_session:
            return jsonify({"status": "Invalid session"})
        
        # TODO generate oauth token and store in temporary table
        # Ideally should be valid for ~1 minute
        # oauth entry: (token: str, generated: date)

        token = "TEMPORARY VALUE"

        return jsonify({"status": "Validated", "oauth_token": token})

    @server.app.route(f"/{AUGUR_API_VERSION}/user/generate_session", methods=['POST'])
    def generate_session():
        # TODO Validate oauth token
        oauth = request.args.get("oauth_token")

        # If invalid, return error JSON:
        # return jsonify({"status": "Invalid oauth token"})

        # If valid, pop oauth token from temporary table
        # Generate user session token to be stored in client browser

        token = "USER SESSION TOKEN"
        user = "USERNAME"

        return jsonify({"status": "Validated", "username": user, "session": token})
    
    @server.app.route(f"/{AUGUR_API_VERSION}/user/query", methods=['POST'])
    def query_user():
        if not development and not request.is_secure:
            return generate_upgrade_request()

        username = request.args.get("username")
        if username is None:
            return jsonify({"status": "Missing argument"}), 400

        if not User.exists(username):
            return jsonify({"status": "Invalid username"})

        return jsonify({"status": True})

    @server.app.route(f"/{AUGUR_API_VERSION}/user/create", methods=['GET', 'POST'])
    def create_user():
        if not development and not request.is_secure:
            return generate_upgrade_request()

        username = request.args.get("username")
        password = request.args.get("password")
        email = request.args.get("email")
        first_name = request.args.get("first_name")
        last_name = request.args.get("last_name")
        admin = request.args.get("create_admin") or False

        result = User.create_user(username, password, email, first_name, last_name, admin)

        return jsonify(result)

    
    @server.app.route(f"/{AUGUR_API_VERSION}/user/remove", methods=['POST', 'DELETE'])
    @login_required
    def delete_user():
        if not development and not request.is_secure:
            return generate_upgrade_request()

        status = current_user.delete()
        return jsonify(status)


    @server.app.route(f"/{AUGUR_API_VERSION}/user/update", methods=['POST'])
    @login_required
    def update_user():
        if not development and not request.is_secure:
            return generate_upgrade_request()

        email = request.args.get("email")
        new_login_name = request.args.get("new_username")
        new_password = request.args.get("new_password")

        if email is not None:
            existing_user = session.query(User).filter(User.email == email).one()
            if existing_user is not None:
                return jsonify({"status": "Already an account with this email"})

            user.email = email
            session.commit()
            return jsonify({"status": "Email Updated"})

        if new_password is not None:
            user.login_hashword = generate_password_hash(new_password)
            session.commit()
            return jsonify({"status": "Password Updated"})

        if new_login_name is not None:
            existing_user = session.query(User).filter(User.login_name == new_login_name).one()
            if existing_user is not None:
                return jsonify({"status": "Username already taken"})

            user.login_name = new_login_name
            session.commit()
            return jsonify({"status": "Username Updated"})

        return jsonify({"status": "Missing argument"}), 400


    @server.app.route(f"/{AUGUR_API_VERSION}/user/add_repo", methods=['GET', 'POST'])
    @login_required
    def add_user_repo():
        if not development and not request.is_secure:
            return generate_upgrade_request()

        repo = request.args.get("repo_url")
        group_name = request.args.get("group_name")

        result = current_user.add_repo(group_name, repo)

        return jsonify(result)


    @server.app.route(f"/{AUGUR_API_VERSION}/user/add_group", methods=['GET', 'POST'])
    @login_required
    def add_user_group():
        if not development and not request.is_secure:
            return generate_upgrade_request()

        group_name = request.args.get("group_name")

        result = current_user.add_group(group_name)

        return jsonify(result)

    @server.app.route(f"/{AUGUR_API_VERSION}/user/remove_group", methods=['GET', 'POST'])
    @login_required
    def remove_user_group():
        if not development and not request.is_secure:
            return generate_upgrade_request()

        group_name = request.args.get("group_name")

        result = current_user.remove_group(group_name)

        return jsonify(result)


    @server.app.route(f"/{AUGUR_API_VERSION}/user/add_org", methods=['GET', 'POST'])
    @login_required
    def add_user_org():
        if not development and not request.is_secure:
            return generate_upgrade_request()

        org = request.args.get("org_url")
        group_name = request.args.get("group_name")

        result = current_user.add_org(group_name, org_url)

        return jsonify(result)


    @server.app.route(f"/{AUGUR_API_VERSION}/user/remove_repo", methods=['GET', 'POST'])
    @login_required
    def remove_user_repo():
        if not development and not request.is_secure:
            return generate_upgrade_request()


        group_name = request.args.get("group_name")
        repo_id = request.args.get("repo_id")

        result = current_user.remove_repo(group_name, repo_id)

        return jsonify(result)


    @server.app.route(f"/{AUGUR_API_VERSION}/user/group_repos", methods=['GET', 'POST'])
    @login_required
    def group_repos():
        """Select repos from a user group by name

        Arguments
        ----------
        username : str
            The username of the user making the request
        group_name : str
            The name of the group to select
        page : int = 0 -> [>= 0]
            The page offset to use for pagination (optional)
        page_size : int = 25 -> [> 0]
            The number of result per page (optional)
        sort : str
            The name of the column to sort the data by (optional)
        direction : str = "ASC" -> ["ASC" | "DESC"]
            The direction to be used for sorting (optional)

        Returns
        -------
        list
            A list of dictionaries containing repos which match the given arguments
        """

        if not development and not request.is_secure:
            return generate_upgrade_request()

        group_name = request.args.get("group_name")
        page = request.args.get("page") or 0
        page_size = request.args.get("page_size") or 25
        sort = request.args.get("sort") or "repo_id"
        direction = request.args.get("direction") or "ASC"

        result = current_user.get_group_repos(group_name, page, page_size, sort, direction)

        return jsonify(result)



    @server.app.route(f"/{AUGUR_API_VERSION}/user/group_repo_count", methods=['GET', 'POST'])
    @login_required
    def group_repo_count():
        """Count repos from a user group by name

        Arguments
        ----------
        username : str
            The username of the user making the request
        group_name : str
            The name of the group to select

        Returns
        -------
        int
            A count of the repos in the given user group
        """

        if not development and not request.is_secure:
            return generate_upgrade_request()

        group_name = request.args.get("group_name")

        result = current_user.group_repo_count(group_name)
        
        return jsonify(result)


    @server.app.route(f"/{AUGUR_API_VERSION}/user/groups", methods=['GET', 'POST'])
    @login_required
    def get_user_groups():
        """Get a list of user groups by username

        Arguments
        ----------
        username : str
            The username of the user making the request

        Returns
        -------
        list
            A list of group names associated with the given username
        """

        if not development and not request.is_secure:
            return generate_upgrade_request()

        result = current_user.get_groups()

        return jsonify(result)


