#!/bin/bash

docker build -t data-review-assistant-ephic-vpn -f Dockerfile .
docker rm -f data-review-assistant-ephic-vpn

docker run -it -d --name data-review-assistant-ephic-vpn --restart=always -v /home/ubuntu/data-review-assistant-v2-9128-ephic-vpn-files/studies:/home/studies -p 9201:8501 data-review-assistant-ephic-vpn

docker logs -f data-review-assistant-ephic-vpn