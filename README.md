# VK to CommerceML
Telegram bot that can synchronize VK products to a website using the CommerceML protocol.

## Build and push docker image
```shell
docker buildx build \
  --tag 'poofeg/vk-to-commerceml:latest' \
  --platform=linux/amd64,linux/arm64 --pull --push .
```
