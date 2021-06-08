"""Copyright 2020 Oakwood Technologies BVBA"""

import random
import string

from automagica.config import ACTIVITIES


class Node:
    """
    Node class reference implementation, all Automagica Flow 
    nodes should ultimately inherit from this class.
    """

    def __init__(self, x=None, y=None, uid=None, label=None):
        """
        Initialize the node
        """
        if not uid:
            uid = self._generate_uid(4)

        self.uid = uid

        self.label = label

        if not x:
            x = 0

        if not y:
            y = 0

        self.x = x
        self.y = y

    def __repr__(self):
        """
        Object representation of the node
        """
        return "<{} {}>".format(self.__class__.__name__, self.uid)

    def __str__(self):
        """
        String representation of the node
        """
        if self.label:
            return self.label
        else:
            return self.__class__.__name__.replace("Node", "")

    def _generate_uid(self, k):
        """
        Generate UID
        TODO: replace with secrets module, this is not cryptographically secure
        and will be flagged by bandit
        """
        return "".join(
            random.choices(
                string.ascii_uppercase
                + string.ascii_lowercase
                + string.digits,
                k=k,
            )
        )

    def to_dict(self):
        """
        Placeholder method to convert the node to a dictionary
        """
        raise NotImplementedError

    def run(self):
        """
        Placeholder method for running the node
        """
        raise NotImplementedError


class StartNode(Node):
    """
    The Start node is always the beginning of an Automagica Flow
    """

    def __init__(self, *args, next_node=None, **kwargs):
        """
        Initialize the Start node
        """
        super().__init__(*args, **kwargs)
        self.next_node = next_node

    def get_next_node(self):
        """
        Method to get the next node
        """
        return self.next_node

    def to_dict(self):
        """
        Method to convert the start node to a dictionary
        """
        return {
            "uid": self.uid,
            "x": self.x,
            "y": self.y,
            "type": self.__class__.__name__,
            "next_node": self.next_node,
            "label": self.label,
        }

    def run(self, bot, on_done=None, on_fail=None):
        """
        Run the Start node
        """
        if on_done:
            on_done(node=self.next_node)


class ActivityNode(Node):
    def __init__(
        self,
        activity,
        *args,
        next_node=None,
        on_exception_node=None,
        class_=None,
        args_=None,
        return_=None,
        **kwargs,
    ):
        """
        Activity node
        """
        super().__init__(*args, **kwargs)

        self.activity = activity

        if not args_:
            args_ = {}

        self.args_ = args_
        self.next_node = next_node
        self.return_ = return_
        self.on_exception_node = on_exception_node

        if self.activity.split(".")[-2][0].isupper():
            class_ = self.activity.split(".")[-2].lower()
            if not self.args_.get("self"):
                self.args_["self"] = class_.lower()

        self.class_ = class_

    def __str__(self):
        """
        String representation for an Activity node
        """
        if self.label:
            return self.label
        else:
            return ACTIVITIES[self.activity]["name"]

    def get_next_node(self):
        """
        Method that returns the next node
        """
        return self.next_node

    def to_dict(self):
        """
        Convert the Activity node to a dictionary
        """
        return {
            "uid": self.uid,
            "x": self.x,
            "y": self.y,
            "type": self.__class__.__name__,
            "next_node": self.next_node,
            "label": self.label,
            "activity": self.activity,
            "args": self.args_,
            "class": self.class_,
            "return_": self.return_,
            "on_exception_node": self.on_exception_node,
        }

    def run(self, bot, on_done=None, on_fail=None):
        """
        Run the Activity node
        """
        args = [
            "{}={}".format(key, val)
            for key, val in self.args_.items()
            if key != "self" and val != None and val != ""
        ]

        command = "# {} ({})\n".format(self, self.uid)

        if self.class_:
            module_ = ".".join(self.activity.split(".")[:-2])
            function_ = self.activity.split(".")[-1]

            command += "from {} import {}\n".format(
                module_, self.activity.split(".")[-2]
            )  # from automagica.activities import Chrome

            if function_ == "__init__":
                command += "{} = {}({})\n".format(
                    self.args_["self"],
                    self.activity.split(".")[-2],
                    ", ".join(args),
                )  # chrome = Chrome()

            else:
                if self.return_:
                    command += "{} = {}.{}({}, {})\n".format(
                        self.return_,
                        self.activity.split(".")[-2],
                        function_,
                        self.args_["self"],
                        ", ".join(args),
                    )  # Chrome.get(chrome, 'https://google.com")
                else:
                    command += "{}.{}({}, {})\n".format(
                        self.activity.split(".")[-2],
                        function_,
                        self.args_["self"],
                        ", ".join(args),
                    )  # Chrome.get(chrome, 'https://google.com")

        else:
            module_ = ".".join(self.activity.split(".")[:-1])
            function_ = self.activity.split(".")[-1]

            command += "from {} import {}\n".format(module_, function_)

            if self.return_:
                command += "{} = {}({})\n".format(
                    self.return_, function_, ", ".join(args)
                )
            else:
                command += "{}({})\n".format(function_, ", ".join(args))

        bot.run(
            command,
            on_done=lambda: on_done(node=self.next_node),
            on_fail=on_fail,
        )


class IfElseNode(Node):
    def __init__(
        self, *args, condition=None, next_node=None, else_node=None, **kwargs
    ):
        super().__init__(**kwargs)
        self.condition = condition
        self.next_node = next_node  # True node
        self.else_node = else_node

    def to_dict(self):
        return {
            "uid": self.uid,
            "x": self.x,
            "y": self.y,
            "type": self.__class__.__name__,
            "next_node": self.next_node,
            "else_node": self.else_node,
            "label": self.label,
            "condition": self.condition,
        }

    def run(self, bot, on_done=None, on_fail=None):
        bot._run_command(f"AUTOMAGICA_RESULT = ({self.condition})")

        if bot.interpreter.locals.get("AUTOMAGICA_RESULT"):
            on_done(node=self.next_node)
        else:
            on_done(node=self.else_node)


class LoopNode(Node):
    def __init__(
        self,
        *args,
        iterable="",
        repeat_n_times=10,
        loop_variable="",
        next_node=None,
        loop_node=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.iterable = iterable
        self.loop_variable = loop_variable
        self.loop_node = loop_node
        self.repeat_n_times = repeat_n_times
        self.next_node = next_node

    def get_next_node(self):
        try:
            # While iterable, iterate
            return next(self.iterable)

        except StopIteration:
            # Reset iterable and go to next node
            self.iterable.seek(0)
            return self.next_node

    def to_dict(self):
        return {
            "uid": self.uid,
            "x": self.x,
            "y": self.y,
            "type": self.__class__.__name__,
            "iterable": self.iterable,
            "loop_variable": self.loop_variable,
            "repeat_n_times": self.repeat_n_times,
            "next_node": self.next_node,
            "loop_node": self.loop_node,
            "label": self.label,
        }

    def run(self, bot, on_done=None, on_fail=None):
        bot.run(self.iterable, on_done=on_done, return_value_when_done=True)


class DotPyFileNode(Node):
    def __init__(
        self,
        *args,
        dotpyfile_path=None,
        next_node=None,
        on_exception_node=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.dotpyfile_path = dotpyfile_path
        self.next_node = next_node
        self.on_exception_node = on_exception_node

    def to_dict(self):
        return {
            "uid": self.uid,
            "x": self.x,
            "y": self.y,
            "type": self.__class__.__name__,
            "next_node": self.next_node,
            "dotpyfile_path": self.dotpyfile_path,
            "on_exception_node": self.on_exception_node,
            "label": self.label,
        }

    def run(self, bot, on_done=None, on_fail=None):
        with open(
            self.dotpyfile_path.replace('"', ""), "r", encoding="utf-8"
        ) as f:
            command = f.read()

        bot.run(command, on_done=lambda: on_done(node=self.next_node))


class CommentNode(Node):
    def __init__(self, *args, comment=None, **kwargs):
        super().__init__(**kwargs)
        self.comment = comment

    def to_dict(self):
        return {
            "uid": self.uid,
            "x": self.x,
            "y": self.y,
            "type": self.__class__.__name__,
            "comment": self.comment,
            "label": self.label,
        }

    def run(self, bot):
        pass


class SubFlowNode(Node):
    def __init__(
        self,
        *args,
        subflow_path=None,
        next_node=None,
        on_exception_node=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.subflow_path = subflow_path
        self.next_node = next_node
        self.on_exception_node = on_exception_node

    def to_dict(self):
        return {
            "uid": self.uid,
            "x": self.x,
            "y": self.y,
            "type": self.__class__.__name__,
            "next_node": self.next_node,
            "on_exception_node": self.on_exception_node,
            "subflow_path": self.subflow_path,
            "label": self.label,
        }


class PythonCodeNode(Node):
    def __init__(
        self,
        *args,
        code=None,
        next_node=None,
        on_exception_node=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.code = code
        self.next_node = next_node
        self.on_exception_node = on_exception_node

    def to_dict(self):
        return {
            "uid": self.uid,
            "x": self.x,
            "y": self.y,
            "type": self.__class__.__name__,
            "next_node": self.next_node,
            "code": self.code,
            "on_exception_node": self.on_exception_node,
            "label": self.label,
        }

    def run(self, bot, on_done=None, on_fail=None):
        bot.run(
            self.code,
            on_done=lambda: on_done(node=self.next_node),
            on_fail=on_fail,
        )
