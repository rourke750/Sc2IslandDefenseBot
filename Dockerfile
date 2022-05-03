FROM python:3.10.0-alpine3.14

RUN mkdir -p /home/appuser/sc2bot

COPY ./ /home/appuser/sc2bot/

WORKDIR /home/appuser/sc2bot

RUN python -m pip install -r requirements.txt

CMD python islanddefense.py