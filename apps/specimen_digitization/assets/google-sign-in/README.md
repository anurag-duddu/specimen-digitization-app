# Google sign-in assets

These assets are used only by the Google authentication action. They do not
change the product typeface, icon registry, or theme.

- `google-g.png` is Google's unmodified standard color gradient G from
  <https://developers.google.com/static/identity/images/g-logo.png>, downloaded
  2026-10-16. SHA-256:
  `d1ce9c2af0b10a7333abc99bc706f9a6a199e5b65bf3e3009624f076b8638e6a`.
- `GoogleSans-Medium.ttf` is a static Latin Medium instance of Google Sans,
  with weight 500, optical size 18 and grade 0. Source:
  <https://raw.githubusercontent.com/google/fonts/main/ofl/googlesans/GoogleSans%5BGRAD%2Copsz%2Cwght%5D.ttf>.
  Downloaded 2026-10-16; original SHA-256:
  `d0a87d835a944b8b40d0e82a5651bb59ab97b936a2aeed5946eb57e7b2a3a90a`.
  The subset SHA-256 is
  `0fa23602aab0038ab7b8c9df163dde722a4ad21c80ad345b0026a78e887c16ae`.
- `OFL.txt` contains the font license text from
  <https://raw.githubusercontent.com/google/fonts/main/ofl/googlesans/OFL.txt>.
  Line endings and trailing whitespace are normalized by repository hooks.
  Copyright 2025 The Google Sans Project Authors. Google Sans is licensed under
  the SIL Open Font License 1.1, without reserved font names.

The source font metadata identifies upstream release v14.000 and source commit
`5c8f512c5fb42a7be099b951a7c097f96209c78e`. Source metadata:
<https://raw.githubusercontent.com/google/fonts/main/ofl/googlesans/METADATA.pb>.

The subset was generated with fontTools 4.61.1 to reduce the bundled asset from
4.7 MB to 113 KiB. It covers the English button and Latin characters; future
localization must include the required character coverage.

```sh
python3 -m fontTools.subset GoogleSans-full.ttf \
  --unicodes=U+0000-024F,U+1E00-1EFF,U+2000-206F,U+20A0-20CF \
  --layout-features='*' --name-IDs='*' --name-legacy --name-languages='*' \
  --output-file=GoogleSans-Latin-Variable.ttf
```

Then instantiate all axes with the same fontTools release:

```python
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
font = TTFont('GoogleSans-Latin-Variable.ttf')
instantiateVariableFont(font, {'wght': 500, 'opsz': 18, 'GRAD': 0}, inplace=True)
font.save('GoogleSans-Medium.ttf')
```

Button colors, font, logo, and padding follow Google's current branding guide:
<https://developers.google.com/identity/branding-guidelines>, updated
2026-07-07. The Google logo is preserved with `BoxFit.contain`. The button uses
real, wrapping text rather than a whole-button raster so text enlargement and
assistive technology remain available. Google brand assets remain subject to
Google's brand guidelines; the font license does not license the Google mark.
