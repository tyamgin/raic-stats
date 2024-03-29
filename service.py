from db import db, db_init
from config import SEASON
from crawler import get_setting

from flask import Flask, jsonify, request
import jinja2
import json
import time


app = Flask(__name__)

templateLoader = jinja2.FileSystemLoader(searchpath="./templates")
templateEnv = jinja2.Environment(loader=templateLoader)


@app.route("/")
def main():
    with db().cursor() as cursor:
        cursor.execute("SELECT DISTINCT kind FROM games")
        kinds = sorted([row['kind'] for row in cursor.fetchall()])

    template = templateEnv.get_template("main.html")
    return template.render(kinds=kinds,
                           users_v=int(time.time() / 3600),
                           last_game_id=get_setting('last_id', 0),
                           season=SEASON)


@app.route("/api/gamesWith/<string:player_name>", methods=['GET'])
def games_with(player_name):
    available_contest_ids = ['0', '1', '2', '3', '4']
    contest_ids = map(lambda x: x if x in available_contest_ids else None,
                      request.args.get('contestIds', type=str, default='').split(','))
    contest_ids = list(filter(lambda x: x, contest_ids))

    kind = request.args.get('kind', type=str, default='')
    versions_count = max(1, min(9999, request.args.get('versionsCount', type=int, default=10)))

    if not contest_ids or not kind:
        result = []
    else:
        with db().cursor() as cursor:
            cursor.execute(f"""SELECT * FROM games WHERE game_id IN
                            (SELECT game_id FROM games WHERE player_name=%s
                                                        AND kind=%s
                                                        AND player_version > (SELECT MAX(player_version) FROM games WHERE player_name=%s) - %s
                                                        AND contest_id IN ({','.join(contest_ids)})
                            )""",
                           (player_name, kind, player_name, versions_count))
            result = [row for row in cursor.fetchall()]
    return jsonify({
        'status': 'OK',
        'result': result
    })


@app.route("/api/users", methods=['GET'])
def users():
    with db().cursor() as cursor:
        cursor.execute("SELECT * FROM users")
        result = [row for row in cursor.fetchall()]
    for row in result:
        if row['avatar'] and not row['avatar'].startswith('http'):
            row['avatar'] = 'https:' + row['avatar']

    if request.args.get('js', type=int, default=0):
        return 'let users_array = {};'.format(json.dumps(result))
    return jsonify({
        'status': 'OK',
        'result': result
    })


@app.before_request
def before_req():
    # don't know wtf is going on, but i need to init db on each query
    # https://stackoverflow.com/questions/33569457/pymysql-returning-old-snapshot-values-not-rerunning-query
    db_init()


if __name__ == "__main__":
    app.run(host='0.0.0.0')

# https://www.digitalocean.com/community/tutorials/how-to-serve-flask-applications-with-gunicorn-and-nginx-on-ubuntu-18-04
# pip3 install git+https://github.com/benoitc/gunicorn.git
#
# gunicorn --bind 0.0.0.0:5000 wsgi:app --workers 4 --bind unix:service.sock
# brew services restart nginx