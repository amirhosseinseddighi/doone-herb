
import enum

from app.models.identity import Roles, User


class Permissions(str, enum.Enum):
    
    # catalog/category
    CATALOG_WRITE = "catalogs:write"

    # products
    PRODUCT_WRITE = "products:write"
    PRODUCT_DELETE = "products:delete"
    
    # orders
    ORDERS_READ_ALL = "orders:read_all"
    ORDERS_FULFILL = "orders:fulfill" # tracking, packed/shipped
    ORDERS_UPDATE_STATUS = "orders:update_status" # arbitrary transitions
    ORDERS_CANCEL_ANY = "orders:cancel_any"
    
    # reviews
    REVIEWS_MODERATE = "reviews:moderate" # reply, edit/delete any
    
    # users
    USERS_READ = "users:read"
    USERS_CHANGE_ROLE = "users:change_role"
    
    # settings
    SETTINGS_WRITE = "settings:write"



ROLE_PERMISSIONS: dict[Roles, frozenset[Permissions]] = {
    Roles.CUSTOMER: frozenset(),
    Roles.PACKER: frozenset({
        Permissions.ORDERS_READ_ALL, 
        Permissions.ORDERS_FULFILL,
        Permissions.ORDERS_UPDATE_STATUS
    }),
    Roles.MANAGER: frozenset({
        Permissions.CATALOG_WRITE,
        Permissions.ORDERS_UPDATE_STATUS,
        Permissions.ORDERS_FULFILL,
        Permissions.ORDERS_READ_ALL,
        Permissions.ORDERS_CANCEL_ANY,
        Permissions.REVIEWS_MODERATE,
        Permissions.USERS_READ,
        Permissions.USERS_CHANGE_ROLE,
        Permissions.PRODUCT_WRITE,
        Permissions.PRODUCT_DELETE
    }),

    Roles.OWNER: frozenset({
        Permissions.CATALOG_WRITE,
        Permissions.ORDERS_UPDATE_STATUS,
        Permissions.ORDERS_FULFILL,
        Permissions.ORDERS_READ_ALL,
        Permissions.ORDERS_CANCEL_ANY,
        Permissions.REVIEWS_MODERATE,
        Permissions.USERS_READ,
        Permissions.USERS_CHANGE_ROLE,
        Permissions.SETTINGS_WRITE,
        Permissions.PRODUCT_WRITE,
        Permissions.PRODUCT_DELETE
    })
}


# which role can asign/delete which role
MANAGEABLE_ROLES: dict[Roles, frozenset[Roles]] = {
    Roles.OWNER:   frozenset({Roles.MANAGER, Roles.PACKER, Roles.CUSTOMER}),
    Roles.MANAGER: frozenset({Roles.PACKER, Roles.CUSTOMER}),
}



def has_perm(user: User, perm: Permissions):
    return perm in ROLE_PERMISSIONS.get(user.role, frozenset())