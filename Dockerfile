FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies (required for Poetry and some Python packages)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Add Poetry to PATH
ENV PATH="/root/.local/bin:${PATH}"

# Copy the backend directory into the container
COPY ./src/backend /app/src/backend
COPY ./src/frontend /app/src/frontend
COPY ./pyproject.toml ./poetry.lock /app/

# Install Python dependencies using Poetry
RUN poetry install --no-root --no-interaction --no-ansi

# Add the src directory to PYTHONPATH
ENV PYTHONPATH="${PYTHONPATH}:/app/src"

# Expose the port FastAPI will run on
EXPOSE 8000

# Command to run the FastAPI app using Uvicorn
CMD ["poetry", "run", "uvicorn", " src.backend.ob_replayer_backend:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]