"""
Structure of event handling mechanism for blinker classes.
Signals can be triggered on class or base level.
"""
from functools import wraps

from blinker import Namespace, ANY


def _merge_dict_class_vars(clz, clz_var:str, limit_clz):
    var = dict()
    for pclz in clz.mro():
        if issubclass(pclz, limit_clz) and hasattr(pclz, clz_var):
            var = {**var, **getattr(pclz, clz_var)}
    return var


class SignalSchema:
    """
    This class holds a signal name and whether the signal should cascade to the base_signal level.
    """
    def __init__(self, name, cascade=False):
        self._name = name
        self._cascade = cascade

    @property
    def name(self):
        return self._name

    @property
    def cascade(self):
        return self._cascade

    def __str__(self):
        return str(self.name)

    def __hash__(self):
        return str(self.name).__hash__()


class CommonSignals:
    """
    Common schemas of signals.
    """
    EXAMPLE = SignalSchema("example", False)


class PointAccessNamespace(Namespace):
    """
    Namespace extension which allows for dot notation access. This enables the possibility to use decorator connection.
    """
    def __getattr__(self, attr):
        return self.get(attr)

    def __setattr__(self, key, value):
        self.__setitem__(key, value)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.__dict__.update({key: value})

    def __delattr__(self, item):
        self.__delitem__(item)

    def __delitem__(self, key):
        super().__delitem__(key)
        del self.__dict__[key]


# signal name for the signal which is triggered / cascaded to for each other signal
EVENT_TRIGGERED = "generic_event"

# all classes which where registered via decorator call
signal_classes = set()

# all base signals
base_signals = PointAccessNamespace()
base_signals.signal(EVENT_TRIGGERED)


def connect_base_signal(name, fn):
    """
    Connect a fn to a base signal with given name
    :param name:
    :param fn:
    :return:
    """
    if name not in base_signals:
        signal = base_signals.signal(name)
    else:
        signal = base_signals.get(name)
    return signal.connect(fn)


def init_class_signals(clz):
    # TODO cleanup signal initialization
    if clz not in signal_classes:
        # Try to add missing signals
        signals_decorator = signals()
        # noinspection PyTypeChecker
        signals_decorator(clz)


def connect_class_signal(clz, name, fn):
    """
    Connect a a fn to a class signal of given class with given name
    :param clz:
    :param name:
    :param fn:
    :return:
    """
    init_class_signals(clz)
    signal = clz.signals().get(name)
    if signal is None:
        raise ValueError("Signal not defined on class " + str(clz))
    return signal.connect(fn)


def connect(*classes, name=None):
    """
    Decorator used to decorate methods which are to connect to signals of the given classes.
    :param name:
    :param classes:
    :return:
    """

    def connect_decorator(fn):
        signal_name = name if name is not None else fn.__name__
        if len(classes) is 0:
            connect_base_signal(signal_name, fn)
        else:
            for clz in classes:
                connect_class_signal(clz, signal_name, fn)
        return fn
    return connect_decorator


def connect_subclasses(*classes, name=None):
    """
    Decorator used to decorate methods which are to connect to signals of the subclasses of the given classes and to
    itself. If no name is given the function name is taken as signal name. :param name: :param clz: :return:
    """

    def connect_decorator(fn):
        @wraps(fn)
        def connect_subclasses_fn(*classes, name=None):
            signal_name = name if name is not None else fn.__name__
            if len(classes) is 0:
                raise ValueError("You need to provide a class to find subclasses to connect to.")
            else:
                subclasses = set()
                for clz in classes:
                    connect_class_signal(clz, signal_name, fn)
                    subclasses.update(clz.__subclasses__())
                for subclass in subclasses:
                    connect_class_signal(subclass, signal_name, fn)
                if subclasses:
                    connect_subclasses_fn(*subclasses, name=signal_name)
            return fn
        return connect_subclasses_fn(*classes, name=name)
    return connect_decorator


def signals(*args):
    """
    Decorator used to decorate classes which are to send signals. The decorator takes either string names of signals
    or schema objects
    :param args:
    :return:
    """

    def signals_decorator(cls):
        schemata = args
        signal_classes.add(cls)

        if hasattr(cls, "signal_namespace"):
            signal_namespace = _merge_dict_class_vars(cls, "signal_namespace", Signaler)
            namespace = PointAccessNamespace()
            # Add signal names to args to be created
            for name in signal_namespace:
                signal = signal_namespace.get(name)
                is_cascading = next((True for x in signal.receivers_for(ANY) if x.__name__ == "cascade"), False)
                schemata = schemata + (SignalSchema(name, is_cascading),)
                # TODO cascade to upper class events too?
        else:
            namespace = PointAccessNamespace()

        for schema in schemata:
            if isinstance(schema, str):
                schema = SignalSchema(schema)
            signal = namespace.signal(schema.name)

            def make_cascade(name):
                def __cascade_padre(sender, **kwargs):
                    base_signals.get(name).send(sender, **kwargs)
                return __cascade_padre

            def make_all_cascade(name):
                def __all_cascade_padre(sender, **kwargs):
                    base_signals.get(name).send(sender, **kwargs)
                return __all_cascade_padre

            if schema.cascade:
                if schema.name not in base_signals:
                    base_signals.signal(schema.name)

                # make_cascade(signal.name)
                setattr(cls, "_cascade_" + schema.name, make_cascade(signal.name))
                signal.connect(getattr(cls, "_cascade_" + schema.name))
            setattr(cls, "_cascade_" + EVENT_TRIGGERED + "_" + schema.name, make_all_cascade(EVENT_TRIGGERED))
            signal.connect(getattr(cls, "_cascade_" + EVENT_TRIGGERED + "_" + schema.name))
        cls.signal_namespace = namespace
        return cls
    return signals_decorator


class SuperStop:
    """
    This class resolves the issue TypeError: object.__init__() takes exactly one argument by being the last class
    in a mro and omitting all arguments. This should be always last in the mro()! In the future this should be solved
    differently.
    """

    def __init__(self, *args, **kwargs):
        mro = self.__class__.mro()
        if SuperStop in mro:
            if len(mro)-2 != mro.index(SuperStop):
                raise ValueError("SuperStop ommitting arguments in " + str(self.__class__)
                                 + " super() callstack: " + str(mro))
        super().__init__()


class Signaler(SuperStop):
    """
    Base class of a class being able to send signals.
    """

    @classmethod
    def send_cls_signal(cls, signal: SignalSchema, *sender, condition=True, **kwargs):
        if condition:
            if len(sender) == 0:
                sender = [cls]
            if signal.name not in cls.signals():
                # Try to add missing signals
                init_class_signals(cls)
                if signal.name not in cls.signals():
                    raise ValueError("Signal is not existing on " + str(cls))
            cls.signals().get(signal.name).send(*sender, signal=signal, **kwargs)

    def send_signal(self, signal: SignalSchema, *sender, condition=True, **kwargs):
        if len(sender) == 0:
            sender = [self]
        self.send_cls_signal(signal, *sender, condition=condition, **kwargs)

    @classmethod
    def signals(cls):
        if not hasattr(cls, "signal_namespace"):
            raise ValueError("Namespace not defined on " + str(cls))
        return getattr(cls, "signal_namespace")
