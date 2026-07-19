# Project Overview

## Backend

- **Framework**: FastAPI is used as the backend framework to handle API requests.
- **Speech Processing**: 
  - **Deepgram** is used for streaming speech-to-text conversion.
- **Retrieval-Augmented Generation (RAG)**: 
  - **Qdrant**: Used as a vector database for storing and retrieving information.
  - **Gemini**: Part of the RAG pipeline for generating responses.
- **WebSockets**: Provides real-time communication over WebSocket, allowing for streaming suggestions based on speech input.

## Frontend

- **React**: The frontend is built using React, which streams microphone input as PCM to the server and displays real-time suggestions.
- **Virtual Audio Device**: To capture both sides of conversations, virtual audio devices like VB-Cable or VoiceMeeter are recommended.

## AI Models and Tools

- **Qdrant**: Used for storage and retrieval in the RAG setup.
- **Deepgram**: Provides the speech-to-text conversion for real-time analysis.
- **Gemini**: An AI tool involved in generating suggestions.

## Environment and Deployment

- **Python 3.11+ and Node 18+**: Required for the backend and frontend respectively.
- **Docker**: Used for running Qdrant, Redis, and managing deployment through Docker Compose.

## Configuration

- **API Keys**: Use a `.env` file to configure necessary API keys like `GEMINI_API_KEY` and `DEEPGRAM_API_KEY`.

## Additional Information

- **Accuracy Improvements**: Involve improving Qdrant data, chunking strategies, and prompts.
- **Latency Optimization**: Placement near Deepgram/Gemini regions and API tuning.
- **Ingest Knowledge**: Scripts available (`app.scripts.ingest_data`) to ingest data into Qdrant.

This setup allows the project to capture and process voice data, provide real-time AI-generated suggestions, and manage deployment and scaling efficiently.