# Database Interfaces
You can use these interfaces on your collection classes, whatever they are, tables in sqlaclhemy-orm or schemas in mongo-engine. They are intended for use with [mixins](./decorator-mixins).

## Identifiable
Anything with an integer primary key can be an Identifiable. The only method (classmethod), `.find_by_id`, needs to find an object of type, implementing the Identifiable type, if noting is found, it should return `None`. Define `not_found_text` to specify the customizable text to use in error messages if the Identifiable is not found. This interface is used in `.database_searcher`.

```py
house_collection: dict[int, House] = {}

class House(Identifiable):
    not_found_text = "House not found"

    def __init__(self, house_id: int, address: str):
        self.address = address
        house_collection[house_id] = self

    @classmethod
    def find_by_id(cls, entry_id: int) -> House | None:
        return house_collection.get(entry_id)
```

## UserRole
Anything used to check if current user exists & is authorized to access some method. This might be the User class itself or something like Admin: a table with only part of the Users. The identity should be the same across the app, unless [TBA](). Interface consists of a classmethod `.find_by_identity`, similar to `Identifiable.find_by_id`; and a instance method `.get_identity` which will be used to extract identity from a UserRole. Define `unauthorized_error` to specify the customizable http code and text to use in error responses. This interface is used in `.jwt_authorizer`.

```py
admin_collection: dict[str, Admin] = {}

class Admin(UserRole):
    unauthorized_error = 403, "Permission denied: U have to be an Admin!"

    def __init__(self, code: str, username: str):
        self.code = code
        self.username = username
        admin_collection[code] = self
    
    @classmethod
    def find_by_identity(cls, identity: str) -> Admin | None:
        return admin_collection.get(identity)

    def get_identity(self) -> str:
        return self.code
```
