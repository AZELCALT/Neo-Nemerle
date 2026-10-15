using System;
using System.Collections.Generic;
using static Nemerle.Collections;
using static Nemerle.Internal;

public static class RuntimeChecks
{
    public static void Main()
    {
        var values = NList.FromArray<int>(new[] { 3, 1, 2 });
        int sum = 0;
        foreach (int value in (IEnumerable<int>)values) sum += value;
        if (sum != 6) throw new Exception("Generic list interface failed");
        System.Collections.Generic.ICollection<int> heap = new Heap<int>(new[] { 3, 1, 2 });
        if (heap.Count != 3 || !heap.Contains(1)) throw new Exception("Heap interface failed");
        try { heap.Remove(1); }
        catch (NotSupportedException) { }
        var constructor = typeof(MappedMemberAttribute).GetConstructor(new[] { typeof(string) });
        var attributes = constructor.GetParameters()[0].GetCustomAttributes(typeof(MappedMemberAttribute), false);
        if (attributes.Length != 1 || ((MappedMemberAttribute)attributes[0]).Name != "Name")
            throw new Exception("Self-applied constructor parameter attribute lost");
        Console.WriteLine("PASS: rebuilt runtime collections, generic interfaces, self-applied attribute");
    }
}
