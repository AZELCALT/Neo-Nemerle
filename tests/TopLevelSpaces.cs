using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;

/// A space is a top-level declaration of its file, so a check that compares a grammar's mapping with an expected value
/// moves the spaces of `public static Run() : int { ... }` to the top level. The host setting
/// NitraSourceConfiguration.SpaceValueTarget = TopLevelSpaces.Target collects each space's value, and Run reads it back
/// as Example.Values[i].
public static class TopLevelSpaces
{
    public const string Target = "Example.Value";
    const string Head = "public static Run() : int { ";
    const string Fields = "public static Values : System.Collections.Generic.List[int] = System.Collections.Generic.List(); "
                        + "public static Value : int { set { Values.Add(value) } } ";
    static readonly Regex Space = new(@"(?<![\w.])space\b(?=\s*(?:[A-Za-z_][\w.]*|\([^)]*\))?\s*(?:as\s+\w+\s*)?(?:\[[^\]]*\]\s*)?\{)");

    static int Close(string text, int open)
    {
        int depth = 0;
        for (int i = open; i < text.Length; i++)
        {
            if (text[i] == '{') depth++;
            else if (text[i] == '}' && --depth == 0) return i;
        }
        throw new ArgumentException("unbalanced braces: " + text);
    }

    public static string Lift(string code)
    {
        int head = code.IndexOf(Head, StringComparison.Ordinal);
        if (head < 0) return code;
        int start = head + Head.Length, end = Close(code, start - 2);
        string body = code.Substring(start, end - start);
        var spaces = new List<string>(); var rest = new StringBuilder(); int p = 0;
        foreach (Match m in Space.Matches(body))
        {
            if (m.Index < p) continue;
            int close = Close(body, body.IndexOf('{', m.Index));
            rest.Append(body, p, m.Index - p).Append("Example.Values[" + spaces.Count + "]");
            spaces.Add(body.Substring(m.Index, close + 1 - m.Index));
            p = close + 1;
        }
        if (spaces.Count == 0) return code;
        rest.Append(body, p, body.Length - p);
        string lifted = code.Substring(0, start) + rest + code.Substring(end);
        lifted = lifted.Replace("public class Example { ", "public class Example { " + Fields);
        return lifted + "\n" + string.Join("\n", spaces) + "\n";
    }

    /// Runs the top-level statements of the file `name` (its spaces), as the program's Main would.
    public static void RunFile(Assembly assembly, string name)
    {
        var main = assembly.GetTypes().Where(t => t.Name == name)
                           .Select(t => t.GetMethod("Main", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static, Type.EmptyTypes))
                           .FirstOrDefault(m => m != null);
        main?.Invoke(null, null);
    }
}
