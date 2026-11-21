Report and form font: Times New Roman.

Order used everywhere (reports, form designer, web client):
  Times New Roman (if installed) -> Tinos (Google Fonts, metric twin of Times New Roman)
  -> Liberation Serif (bundled here, SIL OFL) -> Amiri for Arabic letters.

The web client and the printed reports load Tinos and Amiri from Google Fonts when the server or
browser has internet access. Without internet the bundled LiberationSerif-*.ttf files are used.
The PDF form engine (searchable "Times New Roman" option in the designer) uses the bundled files.

Real Times New Roman is a Microsoft font and cannot be shipped inside the module. To use it on a
Linux server:  sudo apt install ttf-mscorefonts-installer && sudo fc-cache -f -v

Real Times New Roman for printed forms (optional, needs your own licensed copy):
  copy the regular and bold files into this folder as
  TimesNewRoman.ttf + TimesNewRoman-Bold.ttf  (or times.ttf + timesbd.ttf)
  and restart Odoo. The PDF engine then uses them instead of Liberation Serif.

FreeSerifArabic-*.ttf: Arabic + Latin subset of GNU FreeSerif (GPL with font exception).
Used for Arabic text on the printed forms: a Naskh face that sits well with Times.
