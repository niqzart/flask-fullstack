# Upgraded RESTX Parsers

## Updated Base
- Argument class now properly works for arrays of a type with custom `__schema__`
- RequestParser now has class-attributes to specify default argument & result classes
- Bonus: typing for RequestParser's `__init__`

## Prebuilt Parsers
- `counter_parser` designed to be used with `ResourceController.lister` (which provides pagination)
  - `offset` the amount of entries to skip before current
  - `counter` the amount of pages of entries to skip before current
- `password_parser` one parameter, the `password` string
