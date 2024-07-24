FROM python:3.8.8-slim 

COPY . .

RUN pip install -r req.txt

RUN python data_prepare.py

CMD uvicorn --host=0.0.0.0 app:app
