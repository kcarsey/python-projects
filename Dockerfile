FROM python:3.10

EXPOSE 5000
WORKDIR /usr/src/app

RUN git clone --depth 1 https://github.com/kcarsey/python-projects.git .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "appserver:gunicorn_app"]