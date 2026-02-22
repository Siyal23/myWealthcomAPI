FROM python:3.12
WORKDIR /usr/src/app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 3000
CMD ["python", "./APIMain.py"]
