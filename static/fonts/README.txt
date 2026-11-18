Report font: Times New Roman.

wkhtmltopdf uses fonts installed on the Odoo server. If Times New Roman is not installed,
the reports fall back to Liberation Serif (same letter widths), then Tinos.

Linux server (Debian / Ubuntu):
  sudo apt install fonts-liberation          # free, metric-compatible with Times New Roman
  or: sudo apt install ttf-mscorefonts-installer   # the real Times New Roman
  sudo fc-cache -f -v
  restart Odoo
