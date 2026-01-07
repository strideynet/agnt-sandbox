# Devoops React UI

Modern React-based user interface for the Devoops Kubernetes agent.

## Overview

This is a React + TypeScript SPA that provides a clean, responsive interface for:
- Submitting missions to the Devoops agent
- Viewing real-time mission execution logs
- Tracking mission history and status
- OAuth2 authentication via Keycloak

## Tech Stack

- **React 19** with TypeScript
- **Vite** - Fast build tool and dev server
- **React Router** - Client-side routing
- **TanStack Query** - Data fetching with automatic polling
- **Tailwind CSS** - Utility-first styling
- **pnpm** - Fast, disk-efficient package manager

## Architecture

The UI consists of two parts:
1. **React Frontend** (nginx) - Serves static assets and provides the SPA interface
2. **Flask Backend** (Python) - Handles OAuth2 flow and proxies API requests

Both run in the same Kubernetes pod:
- Nginx (port 80) serves React app and proxies `/api/*` and auth endpoints to Flask (port 8080)
- Flask (port 8080) handles OAuth2 callbacks and proxies to the agent

## Development

### Prerequisites

- Node.js 20+
- pnpm (`npm install -g pnpm`)
- Running Flask backend on `localhost:8080`

### Setup

```bash
cd ui-react
pnpm install
```

### Run Development Server

```bash
# Start Flask backend first (in devoops/ui/)
cd ../ui
python app.py  # Runs on port 8080

# Then start React dev server
cd ../ui-react
pnpm dev  # Runs on port 5173
```

Visit http://localhost:5173 - the dev server will proxy API requests to Flask on port 8080.

### Environment Variables

Create a `.env.development` file (already provided):

```env
VITE_API_URL=http://localhost:8080
```

## Building for Production

```bash
pnpm build
```

This creates optimized static files in `dist/`.

## Docker Build

Build the React UI container:

```bash
cd devoops
docker build -t devoops-ui-react:latest -f ui-react/Dockerfile ui-react/
```

## Kubernetes Deployment

The React UI deploys to Kubernetes with the Flask backend:

```bash
# Build both images
docker build -t devoops-ui:latest -f Dockerfile.ui .
docker build -t devoops-ui-react:latest -f ui-react/Dockerfile ui-react/

# Deploy
kubectl apply -k k8s/ui-react/
```

Access at: http://localhost:30901

## Key Features

### Polling-Based Updates

- Mission list polls every 500ms
- Mission detail page polls every 500ms (stops when mission completes/fails)
- Uses TanStack Query's `refetchInterval` for automatic updates

### Authentication

- OAuth2 flow handled by Flask backend
- Sessions stored in Flask (cookies)
- React app redirects to `/login-page` on 401 responses

### Routing

- `/` - Home page (mission form + history)
- `/missions/:id` - Mission detail page
- `/login-page` - Login prompt

## Project Structure

```
ui-react/
├── src/
│   ├── api/
│   │   └── client.ts          # API client with fetch wrapper
│   ├── pages/
│   │   ├── LoginPage.tsx      # Login page
│   │   ├── HomePage.tsx       # Mission list + submission
│   │   └── MissionDetailPage.tsx  # Mission logs + status
│   ├── types/
│   │   └── mission.ts         # TypeScript types
│   ├── App.tsx                # Router setup
│   ├── main.tsx               # Entry point
│   └── index.css              # Tailwind imports
├── public/                     # Static assets
├── Dockerfile                  # Production build
├── nginx.conf                  # Nginx configuration
├── package.json
└── vite.config.ts
```

## Comparison with Old UI

| Feature | Flask UI | React UI |
|---------|----------|----------|
| Technology | Server-side rendered HTML | React SPA |
| Styling | Inline styles (930 lines) | Tailwind CSS |
| Updates | JavaScript polling | TanStack Query |
| Type Safety | None | Full TypeScript |
| Hot Reload | No | Yes (Vite HMR) |
| Bundle Size | N/A | ~200KB gzipped |
| Dev Experience | Template strings | Components + hooks |

## Future Enhancements

The React architecture is ready for:
- **WebSocket support** - Real-time bidirectional communication
- **Interactive missions** - Agent asks questions, user responds
- **Rich UI components** - File uploads, mission templates, etc.
- **State management** - Zustand/Redux when needed
- **Component library** - shadcn/ui, MUI, etc.

## Troubleshooting

### CORS Issues

Make sure Flask backend has `flask-cors` installed and configured:
```python
from flask_cors import CORS
CORS(app, origins=["http://localhost:5173"], supports_credentials=True)
```

### OAuth2 Redirect Issues

Check that `REDIRECT_URI` in Flask matches your deployment:
- Dev: `http://localhost:30900/callback`
- Prod: Update in k8s/ui-react/deployment.yaml

### Build Fails

Clear cache and reinstall:
```bash
rm -rf node_modules pnpm-lock.yaml dist
pnpm install
pnpm build
```
