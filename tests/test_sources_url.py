from app.documents import official_version
import pytest
@pytest.mark.parametrize('ref,version',[('v15.0.0-ee','15.0'),('v17.0.0-ee','17.0'),('8c75d0bf4a4190d94326f1a854d0a102ceca4392','17.0')])
def test_pinned_official_url(ref,version):assert official_version('https://gitlab.com/gitlab-org/gitlab/-/tree/'+ref+'/doc')==version
@pytest.mark.parametrize('url',['http://127.0.0.1/a','https://gitlab.com/other/repo/-/tree/v17.0.0-ee','https://gitlab.com/gitlab-org/gitlab/-/tree/master','https://gitlab.com/gitlab-org/gitlab/-/tree/v17.0.0-ee/doc/user'])
def test_unpinned_or_subset_url_rejected(url):
    with pytest.raises(ValueError):official_version(url)
