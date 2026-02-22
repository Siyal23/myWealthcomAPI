# Use the official Python image from Docker Hub
FROM python:3.12

# Set the working directory inside the container
WORKDIR /usr/src/app

# Copy the entire backend directory (including Main.py and myWealthCom.py)
COPY ./backend /usr/src/app/backend
COPY ./uploads /usr/src/app/uploads

# Install dependencies from requirements.txt
RUN pip install -r ./backend/requirements.txt

# Expose the port FastAPI will run on
EXPOSE 3000

# Run the FastAPI application
CMD ["python", "./backend/Main.py"]
