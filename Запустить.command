#!/bin/zsh
cd "${0:A:h}"
python3 scripts/start.py
if [[ $? -ne 0 ]]; then
  read -r '?Не удалось запустить. Нажмите Enter для закрытия.'
fi
