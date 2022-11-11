# Decorator Mixins

## Aborts
Simple helper for error-handling. Abort is typically an exception-based break of current operation due to a problem, that should be still reported to the client. Aborts usually are planned & documented, so clients know which messages to expect. Both documenting (via the `.doc_abort` decorator) & raising (via the `.abort` helper) aborts is required for decorators bellow, so this interface requires these mechanisms to be implemented. Parameters for both methods are the same: error code (typically a protocol code) and description (aka the error message).

## Database Searcher
Comes within a mixin class for convenience. 

## JWT Authorizer
