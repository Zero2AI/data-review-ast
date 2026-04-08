FROM python:3.11

WORKDIR /home

RUN apt-get update \
        && apt-get install -y vim git curl unzip \
        && apt-get install -y libgl1

COPY . /home

RUN pip install --upgrade pip

RUN chmod +x /home/run.sh

RUN rm -rf Dockerfile restart.sh README.md

CMD /home/run.sh ; sleep infinity