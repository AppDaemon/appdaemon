from logging import Logger

from pydantic import BaseModel


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


def deep_compare(check: dict, data: dict) -> bool:
    """Compares 2 nested dictionaries of values"""
    data = data or {}  # Replaces a None value with an empty dict

    for k, v in tuple(check.items()):
        if isinstance(v, dict) and isinstance(data[k], dict):
            if deep_compare(v, data[k]):
                continue
            else:
                return False
        elif v != data.get(k):
            return False
    else:
        return True


def rreplace(s, old, new, occurrence):
    li = s.rsplit(old, occurrence)
    return new.join(li)


def deepcopy(data):
    result = None

    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[key] = deepcopy(value)

        assert id(result) != id(data)

    elif isinstance(data, list):
        result = []
        for item in data:
            result.append(deepcopy(item))

        assert id(result) != id(data)

    elif isinstance(data, tuple):
        aux = []
        for item in data:
            aux.append(deepcopy(item))
        result = tuple(aux)

        assert id(result) != id(data)

    else:
        result = data

    return result


def deprecation_warnings(model: BaseModel, logger: Logger):
    for field in model.model_fields_set:
        if model.__pydantic_extra__ is not None and field in model.__pydantic_extra__:
            logger.warning(f"Extra config field '{field}'. This will be ignored")
        elif (info := model.model_fields.get(field)) and info.deprecated:
            logger.warning(f"Deprecated field '{field}': {info.deprecation_message}")

        match attr := getattr(model, field):
            case dict():
                for val in attr.values():
                    if isinstance(val, BaseModel):
                        deprecation_warnings(val, logger)
            case BaseModel():
                deprecation_warnings(attr, logger)
