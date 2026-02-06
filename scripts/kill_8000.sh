#!/bin/bash
# Убить все процессы на порту 8000 и проверить результат

pids=$(lsof -ti:8000 2>/dev/null)
if [ -z "$pids" ]; then
  echo "Порт 8000 свободен"
else
  echo "Убиваю процессы: $pids"
  echo "$pids" | xargs kill -9
  sleep 1
  check=$(lsof -ti:8000 2>/dev/null)
  if [ -z "$check" ]; then
    echo "Готово, порт 8000 свободен"
  else
    echo "Не удалось убить: $check"
  fi
fi
