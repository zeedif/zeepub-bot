import uvicorn
import os

if __name__ == "__main__":
    # Ejecutar uvicorn programáticamente
    # reload=True permite recarga en caliente durante desarrollo
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
