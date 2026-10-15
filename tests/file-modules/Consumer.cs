using System;
public static class Consumer
{
    public static void Main()
    {
        if (beta.Run() != 56 || alpha.math.Twice(3) != 6 || alpha.Length("abc") != 3)
            throw new Exception("Module or mask functions failed");
        if (!(new alpha.Node().Other() is beta.Node) || !(new beta.Node().Other() is alpha.Node))
            throw new Exception("Mutual module references failed");
        if (beta.MakePair().Left != 2 || beta.MakePair().Right != 3)
            throw new Exception("Record macro failed");
        if (!typeof(alpha).GetNestedType("hidden", System.Reflection.BindingFlags.NonPublic).IsNestedPrivate)
            throw new Exception("Private mask is exposed in CLR metadata");
        Console.WriteLine("PASS: file modules, masks, mutual references, private helpers, CLR exports, Record macro");
    }
}
