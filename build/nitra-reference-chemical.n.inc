      // A settled recognizer supplies typed fields and original source spans.
      // Construct the same native semantic input without parsing or synthetic
      // source rewriting. The internal chemical implementation stays hidden.
      def recognizedArguments = SCG.List();
      recognizedArguments.Add(<[ sourceProvider ]>);
      recognizedArguments.Add(<[ span ]>);
      foreach(field in fields)
        recognizedArguments.Add(<[ $(field.Name : usesite) ]>);
      _nodeTb.DefineConditional(<[ decl:
        public static CreateRecognizedParseTree(..$ctorParameters) : $(_nodeTb.GetMemType() : typed)
        {
          unchecked($(_chemicalTb.GetMemType() : typed)(..$recognizedArguments))
        }
      ]>);

