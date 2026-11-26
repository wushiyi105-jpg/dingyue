FROM python:3.10-slim

LABEL org.opencontainers.image.source="https://github.com/wushiyi105-jpg/dingyue" \
      org.opencontainers.image.description="订阅 · 账单体检:商户归一、年化、续费日、重复与砍单顺序" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY . .

RUN pip install -e .

EXPOSE 8000

CMD ["python", "-m", "dingyue", "web", "--host", "0.0.0.0"]
