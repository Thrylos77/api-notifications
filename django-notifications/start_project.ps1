py manage.py makemigrations accounts
py manage.py makemigrations notifications
py manage.py migrate
py manage.py collectstatic --noinput
daphne --bind 0.0.0.0 --port 8000 config.asgi:application