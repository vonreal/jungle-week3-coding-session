class HashTable:
    """
    해시 테이블 직접 구현 (파이썬 dict 사용 금지)
    - 내부: 고정 크기 배열(list) + chaining(연결 리스트 또는 list of lists)
    - 해시 함수: 파이썬 내장 hash() 사용 가능
    - load factor 초과 시 동적 resize
    """

    def __init__(self, initial_capacity: int = 16, load_factor: float = 0.75):
        """
        해시 테이블의 시작 상태를 준비하는 함수.

        비유: 사물함 복도를 처음 만들 때,
        사물함 칸 수와 "얼마나 차면 더 크게 늘릴지" 기준을 정하는 단계다.
        처음 구조를 잘 잡아야 나중에 물건을 빠르게 넣고 찾을 수 있다.
        """
        # 버킷 수가 0 이하면 물건을 넣을 칸 자체가 없어서 동작할 수 없다.
        if initial_capacity <= 0:
            raise ValueError("initial_capacity must be greater than 0")

        # load factor는 꽉 찬 정도를 판단하는 기준이라 0보다 커야 한다.
        if load_factor <= 0:
            raise ValueError("load_factor must be greater than 0")

        # 버킷 배열을 먼저 만들고, 아직 저장된 항목 수는 0으로 시작한다.
        self._capacity = initial_capacity
        self._load_factor = load_factor
        self._buckets: list[list[tuple[str, str]]] = [[] for _ in range(self._capacity)]
        self._size = 0

    def set(self, key: str, value: str) -> None:
        """
        키와 값을 저장하는 함수.

        비유: 학생 이름표(key)를 보고 맞는 사물함 칸(bucket)을 찾은 뒤,
        이미 이름표가 있으면 내용물만 바꾸고, 없으면 새로 넣는 과정이다.
        같은 키를 여러 번 넣어도 물건이 복제되지 않게 하려고 덮어쓰기를 먼저 확인한다.
        """
        bucket_index = self._hash(key)
        bucket = self._buckets[bucket_index]

        # 먼저 같은 키가 있는지 확인해서, 있으면 값을 바꿔치기한다.
        for item_index, (stored_key, _) in enumerate(bucket):
            if stored_key == key:
                bucket[item_index] = (key, value)
                return

        # 같은 키가 없으면 이 버킷 끝에 새 항목을 추가한다.
        bucket.append((key, value))
        self._size += 1

        # 너무 빽빽해지면 찾는 속도가 느려질 수 있어서 사물함을 늘린다.
        if self._size / self._capacity > self._load_factor:
            self._resize()

    def get(self, key: str) -> str | None:
        """
        키에 대응하는 값을 찾는 함수.

        비유: 사물함 번호를 계산한 뒤, 그 칸 안에 붙어 있는 이름표들을 훑어보며
        내가 찾는 학생 이름이 있는지 확인하는 과정이다.
        없으면 "그 물건은 없음"을 뜻하는 None을 돌려준다.
        """
        bucket_index = self._hash(key)
        bucket = self._buckets[bucket_index]

        # 같은 버킷 안에 여러 개가 있을 수 있어서 하나씩 비교한다.
        for stored_key, stored_value in bucket:
            if stored_key == key:
                return stored_value

        return None

    def delete(self, key: str) -> bool:
        """
        키에 해당하는 항목을 지우는 함수.

        비유: 사물함 칸 안에서 특정 이름표를 찾아 떼어내는 일이다.
        실제로 지웠는지 아닌지를 알려줘야 이후 코드가 상태를 정확히 알 수 있다.
        """
        bucket_index = self._hash(key)
        bucket = self._buckets[bucket_index]

        # 버킷 안에서 찾은 항목만 정확히 제거한다.
        for item_index, (stored_key, _) in enumerate(bucket):
            if stored_key == key:
                del bucket[item_index]
                self._size -= 1
                return True

        return False

    def exists(self, key: str) -> bool:
        """
        키가 있는지만 빠르게 확인하는 함수.

        비유: 사물함 안 물건 내용까지 꺼내보지 않고,
        이름표가 붙어 있는지만 확인하는 짧은 점검이라고 생각하면 된다.
        """
        return self.get(key) is not None

    def keys(self) -> list[str]:
        """
        저장된 모든 키를 모아서 돌려주는 함수.

        비유: 모든 사물함 칸을 돌면서 이름표만 한 장씩 수집하는 작업이다.
        전체 목록이 필요할 때 한 번에 보여주기 위해 사용한다.
        """
        collected_keys: list[str] = []

        # 버킷을 처음부터 끝까지 돌며 키만 순서대로 모은다.
        for bucket in self._buckets:
            for stored_key, _ in bucket:
                collected_keys.append(stored_key)

        return collected_keys

    def size(self) -> int:
        """
        현재 저장된 항목 수를 알려주는 함수.

        비유: 사물함 복도 전체에 이름표가 몇 장 붙어 있는지 세어둔 숫자를
        바로 보여주는 것이다. 매번 전부 다시 세지 않기 위해 _size를 유지한다.
        """
        return self._size

    def _hash(self, key: str) -> int:
        """
        키를 버킷 번호로 바꾸는 함수.

        비유: 학생 이름을 바로 사물함 번호로 쓰는 대신,
        계산을 한 번 거쳐서 0번부터 마지막 칸 사이 숫자로 바꾸는 과정이다.
        그래야 어떤 키가 들어와도 배열 범위 안에서 자리를 찾을 수 있다.
        """
        # 큰 숫자를 만든 뒤 나머지 연산으로 현재 버킷 범위 안에 맞춘다.
        return hash(key) % self._capacity

    def _resize(self) -> None:
        """
        저장 공간을 2배로 늘리고 다시 배치하는 함수.

        비유: 사물함이 너무 꽉 차면 더 큰 복도로 이사하는 일이다.
        칸 수가 바뀌면 사물함 번호 계산도 달라지므로, 모든 항목을 새 기준으로 다시 넣어야 한다.
        """
        # 기존 데이터를 잠깐 보관해 두고, 새로 더 넓은 버킷 배열을 만든다.
        old_buckets = self._buckets
        self._capacity *= 2
        self._buckets = [[] for _ in range(self._capacity)]
        self._size = 0

        # 예전 데이터를 하나씩 다시 넣어서 새 버킷 위치를 계산한다.
        for bucket in old_buckets:
            for key, value in bucket:
                self.set(key, value)
