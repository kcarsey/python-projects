FROM python:3.10

EXPOSE 5000
WORKDIR /usr/src/app

RUN git clone --depth 1 https://github.com/kcarsey/python-projects.git .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY first-flask-api/app.py .

CMD ["gunicorn", "--bind", "0.0.0.0:5500", "app:gunicorn_app"]