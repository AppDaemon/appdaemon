ARG PYTHON_RELEASE=3.12
ARG BASE_IMAGE=mcr.microsoft.com/devcontainers/python:${PYTHON_RELEASE}
# Runtime image
FROM ${BASE_IMAGE}

# Copy Repo across
COPY . /usr/src/appdaemon/

# Install AD Dependencies
RUN pip install -r /usr/src/appdaemon/requirements.txt

# Add dev dependencies
RUN pip install -r /usr/src/appdaemon/dev-requirements.txt

# Add doc dependencies
RUN pip install -r /usr/src/appdaemon/doc-requirements.txt

# Install AppDaemon itself to keep VSCODE happy

RUN pip install /usr/src/appdaemon
