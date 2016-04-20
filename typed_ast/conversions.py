from typed_ast import ast27
from typed_ast import ast35

def py2to3(ast):
    return _AST2To3().visit(ast)

def _copy_attributes(new_value, old_value):
    attrs = getattr(old_value, '_attributes', None)
    if attrs is not None:
        for attr in attrs:
            setattr(new_value, attr, getattr(old_value, attr))
    return new_value

class _AST2To3(ast27.NodeTransformer):
    # note: None, True, and False are *not* translated into NameConstants.
    # note: Negative numeric literals are not converted to use unary -

    def __init__(self):
        pass

    def visit(self, node):
        """Visit a node."""
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        ret = _copy_attributes(visitor(node), node)
        return ret

    def maybe_visit(self, node):
        if node is not None:
            return self.visit(node)
        else:
            return None

    def generic_visit(self, node):
        class_name = node.__class__.__name__
        converted_class = getattr(ast35, class_name)
        new_node = converted_class()
        for field, old_value in ast27.iter_fields(node):
            if isinstance(old_value, (ast27.AST, list)):
                setattr(new_node, field, self.visit(old_value))
            else:
                setattr(new_node, field, old_value)
        return new_node


    def visit_list(self, l):
        return [self.visit(e) if isinstance(e, (ast27.AST, list)) else e for e in l]

    def visit_FunctionDef(self, n):
        new = self.generic_visit(n)
        new.returns = None
        return new

    def visit_ClassDef(self, n):
        new = self.generic_visit(n)
        new.keywords = []
        return new

    def visit_TryExcept(self, n):
        return ast35.Try(self.visit(n.body),
                         self.visit(n.handlers),
                         self.visit(n.orelse),
                         [])

    def visit_TryFinally(self, n):
        if len(n.body) == 1 and isinstance(n.body[0], ast27.TryExcept):
            new = self.visit(n.body[0])
            new.finalbody = self.visit(n.finalbody)
            return new
        else:
            return ast35.Try(self.visit(n.body),
                             [],
                             [],
                             self.visit(n.finalbody))


    def visit_ExceptHandler(self, n):
        if n.name is None:
            name = None
        elif isinstance(n.name, ast27.Name):
            name = n.name.id
        else:
            raise RuntimeError("'{}' has non-Name name.".format(ast27.dump(n)))

        return ast35.ExceptHandler(self.maybe_visit(n.type),
                                   name,
                                   self.visit(n.body))

    def visit_Print(self, n):
        keywords = []
        if n.dest is not None:
            keywords.append(ast35.keyword("file", self.visit(n.dest)))

        if not n.nl:
            keywords.append(ast35.keyword("end", ast35.Str(" ", lineno=n.lineno, col_offset=-1)))

        return ast35.Expr(ast35.Call(ast35.Name("print", ast35.Load(), lineno=n.lineno, col_offset=-1),
                                     self.visit(n.values),
                                     keywords,
                                     lineno=n.lineno, col_offset=-1))

    def visit_Raise(self, n):
        e = None
        if n.type is not None:
            e = self.visit(n.type)

            if n.inst is not None:
                inst = self.visit(n.inst)
                if isinstance(inst, ast35.Tuple):
                    args = inst.elts
                else:
                    args = [inst]
                e = ast35.Call(e, args, [], lineno=e.lineno, col_offset=-1)

                if n.tback is not None:
                    e = ast35.Call(ast35.Attribute(e, "with_traceback", ast35.Load(), lineno=e.lineno, col_offset=-1),
                                   [self.visit(n.tback)],
                                   [],
                                   lineno=e.lineno, col_offset=-1)
        return ast35.Raise(e, None)

    def visit_Exec(self, n):
        return ast35.Expr(ast35.Call(ast35.Name("exec", ast35.Load(), lineno=n.lineno, col_offset=-1),
                                     [self.visit(n.body), self.maybe_visit(n.globals), self.maybe_visit(n.locals)],
                                     [],
                                     lineno=n.lineno, col_offset=-1))

    # TODO(ddfisher): the name repr could be used locally as something else; disambiguate
    def visit_Repr(self, n):
        return ast35.Call(ast35.Name("repr", ast35.Load(), lineno=n.lineno, col_offset=-1),
                          [self.visit(n.value)],
                          [])

    # TODO(ddfisher): this will cause strange behavior on multi-item with statements with type comments
    def visit_With(self, n):
        return ast35.With([ast35.withitem(self.visit(n.context_expr), self.maybe_visit(n.optional_vars))],
                          self.visit(n.body),
                          n.type_comment)

    def visit_Call(self, n):
        args = self.visit(n.args)
        if n.starargs is not None:
            args.append(ast35.Starred(self.visit(n.starargs), ast35.Load(), lineno=n.starargs.lineno, col_offset=n.starargs.col_offset))

        keywords = self.visit(n.keywords)
        if n.kwargs is not None:
            keywords.append(ast35.keyword(None, self.visit(n.kwargs)))

        return ast35.Call(self.visit(n.func),
                          args,
                          keywords)

    # TODO(ddfisher): find better attributes to give Ellipses
    def visit_Ellipsis(self, n):
        # ellipses in Python 2 only exist as a slice index
        return ast35.Index(ast35.Ellipsis(lineno=-1, col_offset=-1))

    def visit_arguments(self, n):
        def convert_arg(arg):
            if not isinstance(arg, ast27.Name):
                raise RuntimeError("'{}' is not a valid argument.".format(ast27.dump(arg)))
            return ast35.arg(arg.id, None, lineno=arg.lineno, col_offset=arg.col_offset)

        args = [convert_arg(arg) for arg in n.args]

        vararg = None
        if n.vararg is not None:
            vararg = ast35.arg(n.vararg, None, lineno=-1, col_offset=-1)

        kwarg = None
        if n.kwarg is not None:
            kwarg = ast35.arg(n.kwarg, None, lineno=-1, col_offset=-1)

        defaults = self.visit(n.defaults)

        return ast35.arguments(args,
                               vararg,
                               [],
                               [],
                               kwarg,
                               defaults)

    def visit_Str(self, s):
        if isinstance(s.s, bytes):
            return ast35.Bytes(s.s)
        else:
            return ast35.Str(s.s)
