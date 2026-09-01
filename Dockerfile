FROM public.ecr.aws/lambda/python:3.11

WORKDIR ${LAMBDA_TASK_ROOT}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -t ${LAMBDA_TASK_ROOT}

COPY app ${LAMBDA_TASK_ROOT}/app
COPY knowledge ${LAMBDA_TASK_ROOT}/knowledge
COPY scripts ${LAMBDA_TASK_ROOT}/scripts

# Build vector index at image build time (requires OPENAI_API_KEY build arg)
ARG OPENAI_API_KEY
ENV OPENAI_API_KEY=${OPENAI_API_KEY}
ENV CHROMA_PATH=${LAMBDA_TASK_ROOT}/chroma_db
ENV KNOWLEDGE_DIR=${LAMBDA_TASK_ROOT}/knowledge

RUN if [ -n "$OPENAI_API_KEY" ]; then python scripts/build_index.py --output ${LAMBDA_TASK_ROOT}/chroma_db; \
    else echo "WARNING: OPENAI_API_KEY not set — skipping index build"; mkdir -p ${LAMBDA_TASK_ROOT}/chroma_db; fi

CMD ["app.main.handler"]
