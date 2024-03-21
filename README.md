# VK to CcommercMLeml

## Build and push docker image
```shell
docker buildx build \
  --tag 'poofeg/vk-to-commerceml:latest' \
  --platform=linux/amd64,linux/arm64 --pull --push .
```
