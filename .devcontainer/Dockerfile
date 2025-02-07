ARG PYTHON_RELEASE=3.13
ARG BASE_IMAGE=python:${PYTHON_RELEASE}


# Runtime image
FROM ${BASE_IMAGE}

ARG REMOTE_USER
ARG REMOTE_UID
ARG REMOTE_GID

RUN addgroup --gid ${REMOTE_GID} ${REMOTE_USER}
RUN adduser --disabled-password --uid ${REMOTE_UID} --gid ${REMOTE_GID} ${REMOTE_USER}

ENV HOME /home/${REMOTE_USER}

USER ${REMOTE_USER}

# Copy Repo across
COPY . /usr/src/appdaemon/

# Install AD Dependencies
RUN pip install -r /usr/src/appdaemon/requirements.txt

# Add dev dependencies
RUN pip install -r /usr/src/appdaemon/dev-requirements.txt

# Add doc dependencies
RUN pip install -r /usr/src/appdaemon/doc-requirements.txt
