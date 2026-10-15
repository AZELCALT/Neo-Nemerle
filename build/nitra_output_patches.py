"""Reviewed native-source overlays; vendored upstream files remain unchanged."""


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Native output integration anchor changed: ' + old[:100])
    return text.replace(old, new)


def patch(path, text):
    """Add a direct Nemerle expression mapping alongside native AST mappings."""
    name = path.name
    if name == 'AstType.n' and path.parent.name == 'Model':
        text = replace_once(text, '    | Void\n', '    | NemerleExpr\n    | NemerleContext\n    | Void\n')
        text = replace_once(text, '        | (Void,           Void)',
                            '        | (NemerleExpr, NemerleExpr) => true\n        | (NemerleContext, NemerleContext) => true\n        | (Void,           Void)')
        text = replace_once(text, '        | Void          => "void"',
                            '        | NemerleExpr   => "Nemerle.Compiler.Parsetree.PExpr"\n        | NemerleContext => "Nemerle.Compiler.NitraDialectServices.NitraDialectContext"\n        | Void          => "void"')
        return text
    if name == 'TypingUtils-NTypeToAstType.n':
        text = replace_once(text, '    internal NTypeToAstType(t : NType, context : Context) : AstType', '''    private IsNemerleCompilerType(name : NType.Qualified, context : Context, fullName : string) : bool
    {
      def parts = name.Parts;
      if (parts.IsEmpty || parts.Exists(p => !p.TypeArguments.IsEmpty))
        false
      else
      {
        def env = parts.Head.NemerleEnv ?? context.GetNemerleEnvironment();
        match (env.LookupType(parts.Map(p => p.Name)))
        {
          | Some(symbol) => symbol.FullName == fullName
          | None => false
        }
      }
    }

    internal NTypeToAstType(t : NType, context : Context) : AstType''')
        text = replace_once(text, '''            AstType.Ast(t.Location, astSymbol)
          else
''', '''            AstType.Ast(t.Location, astSymbol)
          else if (IsNemerleCompilerType(name, context, "Nemerle.Compiler.Parsetree.PExpr"))
            AstType.NemerleExpr(t.Location)
          else if (IsNemerleCompilerType(name, context, "Nemerle.Compiler.NitraDialectServices.NitraDialectContext"))
            AstType.NemerleContext(t.Location)
          else
''')
        return text
    if name == 'TypingUtils-BindAstSymbolFromMappingExtension.n':
        return replace_once(text, '          | Void => []', '          | NemerleExpr | NemerleContext | Void => []')
    if name == 'SyntaxMappingTyper.n':
        text = replace_once(text, '          | Ast(Void, _) | Undefined', '''          | Ast(NemerleExpr, _) | Ast(NemerleContext, _) => error(exprType, "Use a Nemerle code mapping to access compiler object members.")
          | Ast(Void, _) | Undefined''')
        text = replace_once(text, '\n        | Void => false\n', '\n        | NemerleExpr | NemerleContext | Void => false\n')
        text = replace_once(text, '\n          | Void => false\n', '\n          | NemerleExpr | NemerleContext | Void => false\n')
        text = replace_once(text, '                  | Void                                                                  => assert(false)',
                            '                  | NemerleExpr | NemerleContext | Void                                                    => assert(false)')
        return text
    if name == 'EmitterEnvironment.n':
        return replace_once(text, '      | Void                => <[ void ]>',
                            '      | NemerleExpr         => <[ Nemerle.Compiler.Parsetree.PExpr ]>\n      | NemerleContext      => <[ Nemerle.Compiler.NitraDialectServices.NitraDialectContext ]>\n      | Void                => <[ void ]>')
    if name == 'AstEmitter.n':
        # The native ambiguity machinery cannot manufacture an executable
        # expression. Keep these nodes diagnostic rather than selecting a branch.
        old = '        | _                                 => assert(false)'
        if text.count(old) != 2:
            raise ValueError('Native missing/ambiguous AST construction changed')
        return text.replace(old, '''        | NemerleContext => <[ fun (_) : Nemerle.Compiler.NitraDialectServices.NitraDialectContext { throw System.InvalidOperationException("Cannot manufacture a compiler context from syntax") } ]>
        | NemerleExpr => <[ fun (_) : Nemerle.Compiler.Parsetree.PExpr { throw System.InvalidOperationException("Cannot lower missing or ambiguous syntax to Nemerle") } ]>
''' + old)
    if name == 'DefineMembers-GetAst.n':
        text = replace_once(text,
            '      tb.Define(<[ decl: public override GetAstUntyped()',
            '      unless (syntaxMapping.ReturnType is AstType.NemerleExpr)\n      tb.Define(<[ decl: public override GetAstUntyped()')
        text = replace_once(text, '          if (syntaxMapping.Parameters.IsEmpty)\n',
                            '          if (syntaxMapping.Parameters.IsEmpty && !(syntaxMapping.ReturnType is AstType.NemerleExpr))\n')
        return text
    return None
