using domain.CustomPdm;

namespace CarCanDummy;

// The generated files under docs/car-can-dummy/ (the ID table itself is hand made and only read).
public static class DummyFiles
{
    public static List<(string FileName, string Text)> Generated(IReadOnlyList<DbcBoard> boards, string idTableMarkdown)
    {
        _ = CanIdTableDummy.Parse(idTableMarkdown);
        return
        [
            (LinkPdmDummy.JsonFile, LinkPdmDummy.Json(boards)),
            (LinkPdmDummy.LcsFile, LinkPdmDummy.Lcs(boards))
        ];
    }
}
