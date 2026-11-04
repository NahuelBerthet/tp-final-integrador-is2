"""tp_final_integrador_is2 package."""

from tp_final_integrador_is2.database import (
    CorporateDataRepository,
    CorporateLogRepository,
    get_corporate_data_repository,
    get_corporate_log_repository,
)
from tp_final_integrador_is2.observer import (
    ClientObserver,
    SocketObserver,
    SubscriptionManager,
)
from tp_final_integrador_is2.observerclient import ObserverClient
from tp_final_integrador_is2.proxy import (
    CorporateDataProxy,
    CorporateDataService,
    CorporateServiceInterface,
)
from tp_final_integrador_is2.singletonclient import SingletonClient
from tp_final_integrador_is2.singletonproxyobserver import (
    SingletonProxyObserverServer,
)

__all__ = [
    "ClientObserver",
    "CorporateDataProxy",
    "CorporateDataRepository",
    "CorporateDataService",
    "CorporateLogRepository",
    "CorporateServiceInterface",
    "ObserverClient",
    "SingletonClient",
    "SingletonProxyObserverServer",
    "SocketObserver",
    "SubscriptionManager",
    "get_corporate_data_repository",
    "get_corporate_log_repository",
]
