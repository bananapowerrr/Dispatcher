$env:OLLAMA_API_BASE = "http://127.0.0.1:11434"
Set-Location "G:\Мой диск\AgentBus"
Start-Process -FilePath "C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe" -ArgumentList "-u","G:\Мой диск\AgentBus\dispatcher.py" -WindowStyle Hidden -RedirectStandardOutput "G:\Мой диск\AgentBus\dispatcher.log" -RedirectStandardError "G:\Мой диск\AgentBus\dispatcher.log"